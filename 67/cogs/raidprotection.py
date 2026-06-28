"""
Raid Protection Cog - Detects and responds to raids with lockdown/unlock commands
"""
import discord
from discord import app_commands
from discord.ext import commands, tasks
from config import Config
from database import db
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class RaidProtectionCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.join_history: dict[int, list] = {}
        self.locked_down_channels: set[int] = set()
        self.raid_threshold = 5
        self.raid_window_seconds = 60
        self.raid_watcher.start()
    
    def cog_unload(self):
        self.raid_watcher.cancel()
    
    def has_mod_role(self, interaction: discord.Interaction) -> bool:
        mod_role = discord.utils.get(interaction.guild.roles, id=Config.MODERATOR_ROLE_ID)
        return mod_role in interaction.user.roles if mod_role else False
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Track join times for raid detection"""
        guild_id = member.guild.id
        if guild_id not in self.join_history:
            self.join_history[guild_id] = []
        
        now = datetime.utcnow()
        self.join_history[guild_id].append(now)
        
        # Remove joins older than window
        self.join_history[guild_id] = [
            t for t in self.join_history[guild_id]
            if (now - t).total_seconds() < self.raid_window_seconds
        ]
    
    @tasks.loop(seconds=30)
    async def raid_watcher(self):
        """Check for raid patterns and auto-lock if threshold exceeded"""
        try:
            for guild_id, join_times in list(self.join_history.items()):
                now = datetime.utcnow()
                recent = [t for t in join_times if (now - t).total_seconds() < self.raid_window_seconds]
                
                if len(recent) >= self.raid_threshold:
                    guild = self.bot.get_guild(guild_id)
                    if guild:
                        logger.warning(f"[RAID] Guild {guild.name}: {len(recent)} joins in {self.raid_window_seconds}s")
                        await db.log_event("RAID_PROTECTION", 0, "RAID_DETECTED", f"Joins: {len(recent)}")
        except Exception as e:
            logger.exception(f"Error in raid_watcher: {e}")
    
    @raid_watcher.before_loop
    async def before_raid_watcher(self):
        await self.bot.wait_until_ready()
    
    @app_commands.command(name="raidstatus", description="Check current raid status")
    async def raidstatus(self, interaction: discord.Interaction):
        """Show raid status for current guild"""
        if not interaction.guild:
            await interaction.response.send_message("Not in a guild.", ephemeral=True)
            return
        
        guild_id = interaction.guild.id
        join_times = self.join_history.get(guild_id, [])
        now = datetime.utcnow()
        recent = [t for t in join_times if (now - t).total_seconds() < self.raid_window_seconds]
        
        embed = discord.Embed(
            title="Raid Status",
            description=f"Joins in last {self.raid_window_seconds}s: {len(recent)}",
            color=discord.Color.red() if len(recent) >= self.raid_threshold else discord.Color.green()
        )
        embed.add_field(name="Threshold", value=self.raid_threshold, inline=True)
        embed.add_field(name="Risk Level", value="🔴 HIGH" if len(recent) >= self.raid_threshold else "🟢 SAFE", inline=True)
        embed.add_field(name="Locked Channels", value=len(self.locked_down_channels), inline=True)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="lockdown", description="Lock down all channels (prevent @everyone from sending)")
    @app_commands.describe(reason="Reason for lockdown")
    async def lockdown(self, interaction: discord.Interaction, reason: str = "Raid lockdown"):
        """Lock all channels"""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        if not interaction.guild:
            return
        
        await interaction.response.defer(thinking=True)
        
        locked_count = 0
        try:
            for channel in interaction.guild.channels:
                if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                    try:
                        await channel.set_permissions(
                            interaction.guild.default_role,
                            send_messages=False,
                            speak=False
                        )
                        self.locked_down_channels.add(channel.id)
                        locked_count += 1
                    except Exception as e:
                        logger.error(f"Failed to lock {channel.name}: {e}")
            
            embed = discord.Embed(
                title="🔒 LOCKDOWN ACTIVATED",
                description=f"Locked {locked_count} channels",
                color=discord.Color.red()
            )
            embed.add_field(name="Reason", value=reason)
            embed.add_field(name="Activated by", value=interaction.user.mention)
            
            logs_channel = interaction.guild.get_channel(Config.LOGS_CHANNEL_ID)
            if logs_channel:
                await logs_channel.send(embed=embed)
            
            await interaction.followup.send(embed=embed)
            await db.log_event("RAID_PROTECTION", interaction.user.id, "LOCKDOWN", reason)
        
        except Exception as e:
            logger.exception(f"Error during lockdown: {e}")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="unlock", description="Unlock all channels")
    async def unlock(self, interaction: discord.Interaction):
        """Unlock all channels"""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        if not interaction.guild:
            return
        
        await interaction.response.defer(thinking=True)
        
        unlocked_count = 0
        try:
            for channel in interaction.guild.channels:
                if isinstance(channel, (discord.TextChannel, discord.VoiceChannel)):
                    try:
                        await channel.set_permissions(
                            interaction.guild.default_role,
                            send_messages=None,
                            speak=None
                        )
                        self.locked_down_channels.discard(channel.id)
                        unlocked_count += 1
                    except Exception as e:
                        logger.error(f"Failed to unlock {channel.name}: {e}")
            
            embed = discord.Embed(
                title="🔓 UNLOCK COMPLETE",
                description=f"Unlocked {unlocked_count} channels",
                color=discord.Color.green()
            )
            embed.add_field(name="Restored by", value=interaction.user.mention)
            
            logs_channel = interaction.guild.get_channel(Config.LOGS_CHANNEL_ID)
            if logs_channel:
                await logs_channel.send(embed=embed)
            
            await interaction.followup.send(embed=embed)
            await db.log_event("RAID_PROTECTION", interaction.user.id, "UNLOCK", "Channels restored")
        
        except Exception as e:
            logger.exception(f"Error during unlock: {e}")
            await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(RaidProtectionCog(bot))
