"""
Giveaway Cog - Handles giveaway creation, entries, and automatic ending.
"""
import datetime
import random
from typing import Optional
import logging

import discord
from discord import app_commands
from discord.ext import commands, tasks

from config import Config
from database import db

logger = logging.getLogger(__name__)


class GiveawayModal(discord.ui.Modal, title="Create Giveaway"):
    """Modal for creating giveaways with custom settings."""

    prize = discord.ui.TextInput(label="Prize", placeholder="What is the prize?", required=True)
    duration = discord.ui.TextInput(label="Duration (hours)", placeholder="e.g. 24", required=True)
    winners = discord.ui.TextInput(label="Number of Winners", placeholder="e.g. 1", required=True)
    allowed_roles = discord.ui.TextInput(
        label="Allowed Role IDs",
        placeholder="Comma separated, leave blank for everyone",
        required=False,
    )

    def __init__(self, cog: "GiveawayCog"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            duration_hours = float(self.duration.value)
            winner_count = int(self.winners.value)
            allowed_role_ids = self.cog.parse_allowed_roles(self.allowed_roles.value)
        except ValueError:
            await interaction.response.send_message(
                "Duration must be a number, winners must be an integer, and role IDs must be numeric.",
                ephemeral=True,
            )
            return

        await self.cog.create_giveaway(
            interaction,
            prize=self.prize.value,
            duration_hours=duration_hours,
            winners=winner_count,
            allowed_role_ids=allowed_role_ids,
        )


class GiveawayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def cog_load(self):
        if not self.giveaway_watcher.is_running():
            self.giveaway_watcher.start()

    def cog_unload(self):
        self.giveaway_watcher.cancel()

    def has_mod_role(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        mod_role = discord.utils.get(interaction.guild.roles, id=Config.MODERATOR_ROLE_ID)
        return mod_role in interaction.user.roles if mod_role else False

    @staticmethod
    def parse_allowed_roles(value: Optional[str]) -> list[int]:
        if not value or not value.strip():
            return []
        return [int(role_id.strip()) for role_id in value.split(",") if role_id.strip()]

    @app_commands.command(name="giveaway", description="Create a new giveaway with custom settings")
    @app_commands.describe(
        prize="Prize for the giveaway (leave blank to use modal)",
        duration_hours="Duration in hours",
        winners="Number of winners",
        allowed_roles="Comma-separated role IDs allowed to enter",
    )
    async def giveaway(
        self,
        interaction: discord.Interaction,
        prize: Optional[str] = None,
        duration_hours: Optional[float] = None,
        winners: Optional[int] = 1,
        allowed_roles: Optional[str] = None,
    ):
        """Create giveaway either via parameters or a modal."""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return

        if prize is None or duration_hours is None:
            await interaction.response.send_modal(GiveawayModal(self))
            return

        try:
            allowed_role_ids = self.parse_allowed_roles(allowed_roles)
        except ValueError:
            await interaction.response.send_message("Invalid role IDs provided!", ephemeral=True)
            return

        await self.create_giveaway(interaction, prize, duration_hours, winners or 1, allowed_role_ids)

    async def create_giveaway(
        self,
        interaction: discord.Interaction,
        prize: str,
        duration_hours: float,
        winners: int,
        allowed_role_ids: list[int],
    ):
        if not interaction.guild:
            await interaction.response.send_message("Giveaways can only be created in a server.", ephemeral=True)
            return

        if duration_hours <= 0:
            await interaction.response.send_message("Duration must be greater than 0 hours.", ephemeral=True)
            return

        if winners < 1:
            await interaction.response.send_message("Winners must be at least 1.", ephemeral=True)
            return

        now = datetime.datetime.utcnow()
        ends_at = now + datetime.timedelta(hours=duration_hours)

        embed = discord.Embed(
            title="GIVEAWAY",
            description=f"Prize: {prize}\nDuration: {duration_hours:g} hours\nWinners: {winners}",
            color=discord.Color.gold(),
        )
        embed.add_field(name="Host", value=interaction.user.mention)
        embed.add_field(name="Start Time", value=f"<t:{int(now.timestamp())}>")
        embed.add_field(name="End Time", value=f"<t:{int(ends_at.timestamp())}>")
        embed.add_field(name="Entries", value="0")
        if allowed_role_ids:
            embed.add_field(
                name="Allowed Roles",
                value=", ".join([f"<@&{role_id}>" for role_id in allowed_role_ids]),
                inline=False,
            )
        embed.set_footer(text=f"React with {Config.GIVEAWAY_EMOJI} to enter!")

        if not interaction.response.is_done():
            await interaction.response.defer()

        message = await interaction.followup.send(embed=embed, wait=True)
        await message.add_reaction(Config.GIVEAWAY_EMOJI)

        cursor_id = await db.add_giveaway(
            message.id,
            interaction.channel_id,
            interaction.user.id,
            prize,
            duration_hours,
            winners,
        )
        await db.execute(
            "UPDATE giveaways SET allowed_roles = ?, ends_at = ? WHERE id = ?",
            [",".join(map(str, allowed_role_ids)), ends_at.isoformat(sep=" "), cursor_id],
        )
        await db.log_event(
            "GIVEAWAY",
            interaction.user.id,
            "GIVEAWAY_CREATED",
            f"Prize: {prize}, Duration: {duration_hours}h, Winners: {winners}",
        )

    @tasks.loop(minutes=1)
    async def giveaway_watcher(self):
        for giveaway in await db.get_due_giveaways():
            allowed_roles = self.parse_allowed_roles(giveaway["allowed_roles"])
            await self._end_giveaway_by_ids(
                channel_id=giveaway["channel_id"],
                message_id=giveaway["message_id"],
                winner_count=giveaway["winner_count"],
                allowed_role_ids=allowed_roles,
                giveaway_id=giveaway["id"],
            )

    @giveaway_watcher.before_loop
    async def before_giveaway_watcher(self):
        await self.bot.wait_until_ready()

    async def _end_giveaway_by_ids(
        self,
        channel_id: int,
        message_id: int,
        winner_count: int,
        allowed_role_ids: list[int],
        giveaway_id: Optional[int] = None,
    ):
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, discord.TextChannel):
            if giveaway_id:
                await db.mark_giveaway_inactive(giveaway_id)
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            if giveaway_id:
                await db.mark_giveaway_inactive(giveaway_id)
            return
        except Exception as exc:
            logger.exception(f"Error fetching giveaway message {message_id}: {exc}")
            return

        reaction = discord.utils.get(message.reactions, emoji=Config.GIVEAWAY_EMOJI)
        if not reaction:
            await message.reply("No one entered the giveaway!")
            if giveaway_id:
                await db.mark_giveaway_inactive(giveaway_id)
            return

        entries = [user async for user in reaction.users() if not user.bot]

        if allowed_role_ids:
            valid_entries = []
            for user in entries:
                member = message.guild.get_member(user.id)
                if member and any(role.id in allowed_role_ids for role in member.roles):
                    valid_entries.append(user)
            entries = valid_entries

        if not entries:
            await message.reply("No valid entries for the giveaway!")
            if giveaway_id:
                await db.mark_giveaway_inactive(giveaway_id)
            return

        winners = random.sample(entries, min(winner_count, len(entries)))
        embed = discord.Embed(
            title="GIVEAWAY ENDED",
            description="Winners:\n" + "\n".join(winner.mention for winner in winners),
            color=discord.Color.green(),
        )
        embed.add_field(name="Total Entries", value=str(len(entries)), inline=False)

        await message.reply(embed=embed)

        if giveaway_id:
            await db.mark_giveaway_inactive(giveaway_id)

        await db.log_event(
            event_type="GIVEAWAY",
            user_id=message.author.id,
            action="GIVEAWAY_ENDED",
            details=f"Winners: {len(winners)}, Entries: {len(entries)}",
        )


async def setup(bot):
    await bot.add_cog(GiveawayCog(bot))
