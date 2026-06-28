"""
Partners Cog - Handles partner system registration and logging with modal GUI
"""
import discord
from discord import app_commands
from discord.ext import commands
import logging
from typing import Optional
from datetime import datetime
from config import Config
from database import db

logger = logging.getLogger(__name__)


class PartnerModal(discord.ui.Modal, title="Partnership Registration"):
    server_name = discord.ui.TextInput(
        label="Server Name",
        required=True,
        max_length=100
    )
    robux_reward = discord.ui.TextInput(
        label="Robux Reward",
        required=True
    )
    member_count = discord.ui.TextInput(
        label="Member Count",
        required=True
    )
    partner_message = discord.ui.TextInput(
        label="Partnership Message",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1024
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            robux_amt = int(self.robux_reward.value)
            member_amt = int(self.member_count.value)
        except ValueError:
            await interaction.response.send_message(
                "Robux and Member Count must be numbers!",
                ephemeral=True
            )
            return

        try:
            await db.execute(
                """
                INSERT INTO partners
                (server_name, robux_reward, member_count, partner_message, submitted_by, created_at, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    self.server_name.value,
                    robux_amt,
                    member_amt,
                    self.partner_message.value,
                    interaction.user.id,
                    datetime.utcnow(),
                    "approved"
                ]
            )

            partners_channel = interaction.guild.get_channel(
                Config.PARTNERS_CHANNEL_ID
            )
            if partners_channel:
                await partners_channel.send(self.partner_message.value)

            await interaction.response.send_message(
                "Partnership geplaatst.",
                ephemeral=True
            )

            await db.log_event(
                "PARTNER",
                interaction.user.id,
                "CREATE",
                f"Created partner {self.server_name.value}"
            )

        except Exception as e:
            logger.exception("Error submitting partnership")
            await interaction.response.send_message(
                f"Error submitting partnership: {e}",
                ephemeral=True
            )


class PartnerCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _is_marketing(self, interaction: discord.Interaction) -> bool:
        marketing_role = discord.utils.get(
            interaction.guild.roles,
            id=Config.MARKETING_ROLE_ID
        )
        return marketing_role and marketing_role in interaction.user.roles

    @app_commands.command(name="partner", description="Submit a partnership")
    async def partner(self, interaction: discord.Interaction):
        if not self._is_marketing(interaction):
            await interaction.response.send_message(
                "Only marketing team can submit partnerships!",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(PartnerModal())

    @app_commands.command(name="partnerlogs", description="View partnership logs")
    async def partnerlogs(
        self,
        interaction: discord.Interaction,
        user: Optional[discord.User] = None
    ):
        try:
            if user:
                result = await db.fetch_all(
                    """
                    SELECT server_name, robux_reward, member_count
                    FROM partners
                    WHERE submitted_by = ?
                    ORDER BY id DESC
                    LIMIT 50
                    """,
                    [user.id]
                )
            else:
                result = await db.fetch_all(
                    """
                    SELECT server_name, robux_reward, member_count
                    FROM partners
                    ORDER BY id DESC
                    LIMIT 10
                    """
                )

            embed = discord.Embed(
                title="Partnership Logs",
                color=0xE0E0E0,
                description=f"Showing partnership history"
            )

            if result:
                for server_name, robux, members in result:
                    embed.add_field(
                        name=server_name,
                        value=f"Reward: R$ {robux:,} | Members: {members}",
                        inline=False
                    )
            else:
                embed.add_field(
                    name="Info",
                    value="No partnerships recorded.",
                    inline=False
                )
            
            embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot")

            await interaction.response.send_message(
                embed=embed,
                ephemeral=True
            )

        except Exception as e:
            logger.exception("Error fetching partnership logs")
            await interaction.response.send_message(
                f"Error fetching logs: {e}",
                ephemeral=True
            )

    @app_commands.command(
        name="deletepartners",
        description="Delete all partner logs from a specific user"
    )
    @app_commands.describe(user="User whose partner logs should be deleted")
    async def deletepartners(
        self,
        interaction: discord.Interaction,
        user: discord.User
    ):
        if not self._is_marketing(interaction):
            await interaction.response.send_message(
                "Only marketing team can delete partner logs!",
                ephemeral=True
            )
            return

        try:
            await db.execute(
                "DELETE FROM partners WHERE submitted_by = ?",
                [user.id]
            )

            await interaction.response.send_message(
                f"All partner logs from {user.mention} have been deleted.",
                ephemeral=True
            )

            await db.log_event(
                "PARTNER",
                interaction.user.id,
                "DELETE",
                f"Deleted partner logs from user {user.id}"
            )

        except Exception as e:
            logger.exception("Error deleting partner logs")
            await interaction.response.send_message(
                f"Error deleting partner logs: {e}",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(PartnerCog(bot))
