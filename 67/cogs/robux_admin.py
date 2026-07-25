"""
Robux Admin Cog - tools for staff to review and resolve Robux verifications
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands
from discord.ext import commands

from database import db
import aiosqlite
from discord.ui import Modal, TextInput
from config import Config

logger = logging.getLogger(__name__)


class RobuxAdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name='list_robux', description='List pending Robux verifications')
    async def list_robux(self, interaction: discord.Interaction):
        if not (interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message('No permission.', ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        rows = await db.fetch_pending_robux_verifications()
        if not rows:
            await interaction.followup.send('No pending verifications.', ephemeral=True)
            return

        lines = []
        for r in rows:
            lines.append(f"{r['id']}: product={r['product_id']} user={r['user_id']} created={r['created_at']}")

        await interaction.followup.send('\n'.join(lines), ephemeral=True)

    @app_commands.command(name='resolve_robux', description='Approve or reject a Robux verification')
    @app_commands.describe(verification_id='Verification ID', approve='Approve?')
    async def resolve_robux(self, interaction: discord.Interaction, verification_id: int, approve: bool):
        if not (interaction.user.guild_permissions.manage_guild or interaction.user.guild_permissions.administrator):
            await interaction.response.send_message('No permission.', ephemeral=True)
            return

        # Open a modal to collect optional notes from the reviewer
        class ResolveModal(Modal, title=f"Resolve #{verification_id}"):
            notes = TextInput(label='Notes', style=discord.TextStyle.long, required=False)

            async def on_submit(self, modal_interaction: discord.Interaction):
                note_text = self.notes.value
                try:
                    await db.resolve_robux_verification(verification_id, approve, interaction.user.id, notes=note_text)

                    if approve:
                        # deliver as above
                        async with aiosqlite.connect(db.db_path) as conn:
                            conn.row_factory = aiosqlite.Row
                            async with conn.execute('SELECT product_id, user_id FROM robux_verifications WHERE id = ?', (verification_id,)) as cursor:
                                row = await cursor.fetchone()
                                if row:
                                    product_id = row['product_id']
                                    user_id = row['user_id']
                                    store = self.view.bot.get_cog('StoreCog') if hasattr(self.view, 'bot') else None
                                    store = self.view.bot.get_cog('StoreCog') if self.view and hasattr(self.view, 'bot') else None
                                    if store:
                                        await store.deliver_product_to_user(product_id, user_id, f'robux-{verification_id}', 'robux')

                    await interaction.followup.send('Verification resolved.', ephemeral=True)
                except Exception:
                    logger.exception('Failed resolving verification via modal')
                    await interaction.followup.send('Failed to resolve.', ephemeral=True)

        modal = ResolveModal()
        await interaction.response.send_modal(modal)


async def setup(bot: commands.Bot):
    await bot.add_cog(RobuxAdminCog(bot))
