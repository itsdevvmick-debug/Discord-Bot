"""
Moderation Cog - Handles all moderation commands
"""
import discord
from discord import app_commands
from discord.ext import commands
from config import Config
from database import db
from typing import Optional
import datetime
import logging

logger = logging.getLogger(__name__)

class ModerationCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    def has_mod_role(self, interaction: discord.Interaction) -> bool:
        """Check if user has moderator role"""
        mod_role = discord.utils.get(interaction.guild.roles, id=Config.MODERATOR_ROLE_ID)
        return mod_role in interaction.user.roles if mod_role else False
    
    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="Member to kick", reason="Reason for kick")
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        """Kick a member"""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        reason = reason or "No reason provided"
        await member.kick(reason=reason)
        
        embed = discord.Embed(
            title="Member Kicked",
            description=f"{member.mention} has been removed",
            color=0xE0E0E0
        )
        embed.add_field(name="Reason", value=reason)
        embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot")
        
        await interaction.response.send_message(embed=embed)
        await db.log_event("MODERATION", interaction.user.id, "KICK", f"Kicked {member.id}: {reason}")
    
    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="Member to ban", reason="Reason for ban")
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        """Ban a member"""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        reason = reason or "No reason provided"
        await member.ban(reason=reason)
        
        embed = discord.Embed(
            title="Member Banned",
            description=f"{member.mention} has been removed",
            color=0xE0E0E0
        )
        embed.add_field(name="Reason", value=reason)
        embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot")
        
        await interaction.response.send_message(embed=embed)
        await db.log_event("MODERATION", interaction.user.id, "BAN", f"Banned {member.id}: {reason}")
    
    @app_commands.command(name="unban", description="Unban a user from the server")
    @app_commands.describe(user="User ID to unban", reason="Reason for unban")
    async def unban(self, interaction: discord.Interaction, user: str, reason: Optional[str] = None):
        """Unban a user"""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        try:
            user_id = int(user)
            user_obj = await self.bot.fetch_user(user_id)
            await interaction.guild.unban(user_obj)
            reason = reason or "No reason provided"
            
            embed = discord.Embed(
                title="Member Unbanned",
                description=f"{user_obj.mention} has been unbanned",
                color=0xE0E0E0
            )
            embed.add_field(name="Reason", value=reason)
            embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot")
            
            await interaction.response.send_message(embed=embed)
            await db.log_event("MODERATION", interaction.user.id, "UNBAN", f"Unbanned {user_id}: {reason}")
        except ValueError:
            await interaction.response.send_message("Invalid user ID provided!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="purge", description="Delete messages from a channel")
    @app_commands.describe(amount="Number of messages to delete")
    async def purge(self, interaction: discord.Interaction, amount: int):
        """Purge messages"""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        if amount > 100:
            await interaction.response.send_message("Can only delete up to 100 messages at a time!", ephemeral=True)
            return
        
        deleted = await interaction.channel.purge(limit=amount)
        
        await interaction.response.send_message(f"Deleted {len(deleted)} messages", ephemeral=True)
        await db.log_event("MODERATION", interaction.user.id, "PURGE", f"Deleted {len(deleted)} messages in {interaction.channel.name}")
    
    @app_commands.command(name="mute", description="Mute a member")
    @app_commands.describe(member="Member to mute", minutes="Duration in minutes")
    async def mute(self, interaction: discord.Interaction, member: discord.Member, minutes: int):
        """Mute a member"""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        if minutes < 1 or minutes > 40320:
            await interaction.response.send_message("Minutes must be between 1 and 40320.", ephemeral=True)
            return

        duration = discord.utils.utcnow() + datetime.timedelta(minutes=minutes)
        await member.edit(timeout=duration, reason=f"Muted by {interaction.user}")
        
        embed = discord.Embed(
            title="Member Muted",
            description=f"{member.mention} has been muted for {minutes} minutes",
            color=0xE0E0E0
        )
        embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot")
        
        await interaction.response.send_message(embed=embed)
        await db.log_event("MODERATION", interaction.user.id, "MUTE", f"Muted {member.id} for {minutes} minutes")
    
    @app_commands.command(name="unmute", description="Unmute a member")
    @app_commands.describe(member="Member to unmute")
    async def unmute(self, interaction: discord.Interaction, member: discord.Member):
        """Unmute a member"""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        await member.edit(timeout=None)
        
        embed = discord.Embed(
            title="Member Unmuted",
            description=f"{member.mention} has been unmuted",
            color=0xE0E0E0
        )
        embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot")
        
        await interaction.response.send_message(embed=embed)
        await db.log_event("MODERATION", interaction.user.id, "UNMUTE", f"Unmuted {member.id}")
    
    @app_commands.command(name="membercount", description="Get server member count")
    async def membercount(self, interaction: discord.Interaction):
        """Get member count"""
        embed = discord.Embed(
            title="Server Statistics",
            color=0xE0E0E0
        )
        embed.add_field(name="Total Members", value=interaction.guild.member_count)
        embed.add_field(name="Users", value=len([m for m in interaction.guild.members if not m.bot]))
        embed.add_field(name="Bots", value=len([m for m in interaction.guild.members if m.bot]))
        embed.add_field(name="Roles", value=len(interaction.guild.roles))
        embed.add_field(name="Channels", value=len(interaction.guild.channels))
        embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="serverinfo", description="Get server information")
    async def serverinfo(self, interaction: discord.Interaction):
        """Get server info"""
        embed = discord.Embed(
            title=f"Server: {interaction.guild.name}",
            color=0xE0E0E0
        )
        embed.add_field(name="Server ID", value=interaction.guild.id)
        embed.add_field(name="Owner", value=interaction.guild.owner.mention if interaction.guild.owner else "Unknown")
        embed.add_field(name="Created", value=f"<t:{int(interaction.guild.created_at.timestamp())}>")
        embed.add_field(name="Members", value=interaction.guild.member_count)
        embed.add_field(name="Users", value=len([m for m in interaction.guild.members if not m.bot]))
        embed.add_field(name="Bots", value=len([m for m in interaction.guild.members if m.bot]))
        embed.add_field(name="Roles", value=len(interaction.guild.roles))
        embed.add_field(name="Channels", value=len(interaction.guild.channels))
        embed.add_field(name="Text Channels", value=len([c for c in interaction.guild.channels if isinstance(c, discord.TextChannel)]))
        embed.add_field(name="Voice Channels", value=len([c for c in interaction.guild.channels if isinstance(c, discord.VoiceChannel)]))
        embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
        embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot")
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="addrole", description="Add a role to a member")
    @app_commands.describe(member="Member to give role to", role="Role to add")
    async def addrole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        """Add role to member"""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        if role in member.roles:
            await interaction.response.send_message(f"{member.mention} already has {role.mention}", ephemeral=True)
            return
        
        await member.add_roles(role)
        
        await interaction.response.send_message(f"Added {role.mention} to {member.mention}")
        await db.log_event("MODERATION", interaction.user.id, "ADD_ROLE", f"Added {role.id} to {member.id}")
    
    @app_commands.command(name="removerole", description="Remove a role from a member")
    @app_commands.describe(member="Member to remove role from", role="Role to remove")
    async def removerole(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        """Remove role from member"""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        if role not in member.roles:
            await interaction.response.send_message(f"{member.mention} doesn't have {role.mention}", ephemeral=True)
            return
        
        await member.remove_roles(role)
        
        await interaction.response.send_message(f"Removed {role.mention} from {member.mention}")
        await db.log_event("MODERATION", interaction.user.id, "REMOVE_ROLE", f"Removed {role.id} from {member.id}")
    
    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(member="Member to warn", reason="Reason for warning")
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        """Warn a member"""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        reason = reason or "No reason provided"
        embed = discord.Embed(
            title="Member Warning",
            description=f"{member.mention} has been warned",
            color=0xE0E0E0
        )
        embed.add_field(name="Reason", value=reason)
        embed.add_field(name="Warned by", value=interaction.user.mention)
        embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot")
        
        await interaction.response.send_message(embed=embed)
        await db.log_event("MODERATION", interaction.user.id, "WARN", f"Warned {member.id}: {reason}")
    
    @app_commands.command(name="slowmode", description="Set slowmode for current channel")
    @app_commands.describe(seconds="Slowmode duration in seconds (0 to disable)")
    async def slowmode(self, interaction: discord.Interaction, seconds: int):
        """Set channel slowmode"""
        if not self.has_mod_role(interaction):
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        await interaction.channel.edit(slowmode_delay=seconds)
        
        if seconds == 0:
            await interaction.response.send_message("Slowmode has been disabled")
        else:
            await interaction.response.send_message(f"Slowmode set to {seconds} seconds")
        
        await db.log_event("MODERATION", interaction.user.id, "SLOWMODE", f"Set slowmode to {seconds}s in {interaction.channel.name}")

async def setup(bot):
    await bot.add_cog(ModerationCog(bot))
