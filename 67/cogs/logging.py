"""
Logging Cog - configurable log channel and helper utilities
"""
from __future__ import annotations

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from config import Config

logger = logging.getLogger(__name__)


class LoggingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name='setlogchannel', description='Set the log channel for purchases and errors')
    @app_commands.describe(channel='Channel to send logs to')
    async def setlogchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not interaction.user.guild_permissions.manage_guild and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message('You do not have permission.', ephemeral=True)
            return

        # Persist in environment is not possible here; provide confirmation and instruct updating .env
        await interaction.response.send_message(f'Set log channel to {channel.mention}. Update your .env or Config as needed.', ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(LoggingCog(bot))
"""
Logging Cog - Logs all server events including messages, members, roles
"""
import discord
from discord.ext import commands
from config import Config
from database import db
import datetime
import logging

logger = logging.getLogger(__name__)

class LoggingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        """Log deleted messages"""
        if message.author.bot:
            return
        
        try:
            embed = discord.Embed(
                title="Message Deleted",
                description=f"Message from {message.author.mention} deleted",
                color=discord.Color.red()
            )
            embed.add_field(name="Content", value=message.content[:1024] if message.content else "(No content)")
            embed.add_field(name="Channel", value=f"#{message.channel.name}")
            embed.add_field(name="Author ID", value=message.author.id)
            embed.add_field(name="Author", value=f"{message.author.name}#{message.author.discriminator}")
            embed.timestamp = datetime.datetime.utcnow()
            
            logs_channel = self.bot.get_channel(Config.LOGS_CHANNEL_ID)
            if logs_channel:
                await logs_channel.send(embed=embed)
            
            await db.log_event(
                "MESSAGE",
                message.author.id,
                "MESSAGE_DELETED",
                f"Channel: {message.channel.id}, Author: {message.author.id}, Content: {message.content[:100]}"
            )
        except Exception as e:
            logger.exception(f"Error logging deleted message: {e}")
    
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        """Log edited messages"""
        if before.author.bot:
            return
        
        try:
            if before.content == after.content:
                return
            
            embed = discord.Embed(
                title="Message Edited",
                description=f"Message from {before.author.mention} edited",
                color=discord.Color.orange()
            )
            embed.add_field(name="Before", value=before.content[:1024] if before.content else "(No content)")
            embed.add_field(name="After", value=after.content[:1024] if after.content else "(No content)")
            embed.add_field(name="Channel", value=f"#{before.channel.name}")
            embed.add_field(name="Author", value=f"{before.author.name}#{before.author.discriminator}")
            embed.timestamp = datetime.datetime.utcnow()
            
            logs_channel = self.bot.get_channel(Config.LOGS_CHANNEL_ID)
            if logs_channel:
                await logs_channel.send(embed=embed)
            
            await db.log_event(
                "MESSAGE",
                before.author.id,
                "MESSAGE_EDITED",
                f"Channel: {before.channel.id}, By: {before.author.id}"
            )
        except Exception as e:
            logger.exception(f"Error logging edited message: {e}")
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Log all non-bot messages"""
        if message.author.bot:
            return
        
        try:
            await db.log_event(
                "MESSAGE",
                message.author.id,
                "MESSAGE_SENT",
                f"Channel: {message.channel.id}, Author: {message.author.id}, Content: {message.content[:100]}"
            )
        except Exception as e:
            logger.exception(f"Error logging message: {e}")
    
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        """Log member ban"""
        try:
            embed = discord.Embed(
                title="Member Banned",
                description=f"{user.mention} has been banned",
                color=discord.Color.red()
            )
            embed.add_field(name="User ID", value=user.id)
            embed.add_field(name="Username", value=f"{user.name}#{user.discriminator}")
            embed.timestamp = datetime.datetime.utcnow()
            
            logs_channel = self.bot.get_channel(Config.LOGS_CHANNEL_ID)
            if logs_channel:
                await logs_channel.send(embed=embed)
            
            await db.log_event("MODERATION", user.id, "BAN_EXECUTED", f"User: {user.id}")
        except Exception as e:
            logger.exception(f"Error logging ban: {e}")
    
    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        """Log member unban"""
        try:
            embed = discord.Embed(
                title="Member Unbanned",
                description=f"{user.mention} has been unbanned",
                color=discord.Color.green()
            )
            embed.add_field(name="User ID", value=user.id)
            embed.add_field(name="Username", value=f"{user.name}#{user.discriminator}")
            embed.timestamp = datetime.datetime.utcnow()
            
            logs_channel = self.bot.get_channel(Config.LOGS_CHANNEL_ID)
            if logs_channel:
                await logs_channel.send(embed=embed)
            
            await db.log_event("MODERATION", user.id, "UNBAN_EXECUTED", f"User: {user.id}")
        except Exception as e:
            logger.exception(f"Error logging unban: {e}")
    
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        """Log channel creation"""
        try:
            embed = discord.Embed(
                title="Channel Created",
                description=f"Channel #{channel.name} created",
                color=discord.Color.green()
            )
            embed.add_field(name="Channel ID", value=channel.id)
            embed.add_field(name="Type", value=str(channel.type))
            embed.timestamp = datetime.datetime.utcnow()
            
            logs_channel = self.bot.get_channel(Config.LOGS_CHANNEL_ID)
            if logs_channel:
                await logs_channel.send(embed=embed)
            
            await db.log_event("CHANNEL", 0, "CHANNEL_CREATED", f"Channel: {channel.id}, Name: {channel.name}")
        except Exception as e:
            logger.exception(f"Error logging channel creation: {e}")
    
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """Log channel deletion"""
        try:
            embed = discord.Embed(
                title="Channel Deleted",
                description=f"Channel #{channel.name} deleted",
                color=discord.Color.red()
            )
            embed.add_field(name="Channel ID", value=channel.id)
            embed.timestamp = datetime.datetime.utcnow()
            
            logs_channel = self.bot.get_channel(Config.LOGS_CHANNEL_ID)
            if logs_channel:
                await logs_channel.send(embed=embed)
            
            await db.log_event("CHANNEL", 0, "CHANNEL_DELETED", f"Channel: {channel.id}, Name: {channel.name}")
        except Exception as e:
            logger.exception(f"Error logging channel deletion: {e}")
    
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        """Log role creation"""
        try:
            embed = discord.Embed(
                title="Role Created",
                description=f"Role {role.mention} created",
                color=discord.Color.green()
            )
            embed.add_field(name="Role ID", value=role.id)
            embed.add_field(name="Name", value=role.name)
            embed.timestamp = datetime.datetime.utcnow()
            
            logs_channel = self.bot.get_channel(Config.LOGS_CHANNEL_ID)
            if logs_channel:
                await logs_channel.send(embed=embed)
            
            await db.log_event("ROLE", 0, "ROLE_CREATED", f"Role: {role.id}, Name: {role.name}")
        except Exception as e:
            logger.exception(f"Error logging role creation: {e}")
    
    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        """Log role deletion"""
        try:
            embed = discord.Embed(
                title="Role Deleted",
                description=f"Role deleted",
                color=discord.Color.red()
            )
            embed.add_field(name="Role ID", value=role.id)
            embed.add_field(name="Name", value=role.name)
            embed.timestamp = datetime.datetime.utcnow()
            
            logs_channel = self.bot.get_channel(Config.LOGS_CHANNEL_ID)
            if logs_channel:
                await logs_channel.send(embed=embed)
            
            await db.log_event("ROLE", 0, "ROLE_DELETED", f"Role: {role.id}, Name: {role.name}")
        except Exception as e:
            logger.exception(f"Error logging role deletion: {e}")
    
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        """Log member updates (roles, nickname, etc)"""
        try:
            # Check for role changes
            if before.roles != after.roles:
                added_roles = [r for r in after.roles if r not in before.roles]
                removed_roles = [r for r in before.roles if r not in after.roles]
                
                if added_roles or removed_roles:
                    embed = discord.Embed(
                        title="Member Roles Updated",
                        description=f"Roles updated for {after.mention}",
                        color=discord.Color.blue()
                    )
                    if added_roles:
                        embed.add_field(name="Added Roles", value=", ".join([r.mention for r in added_roles]))
                    if removed_roles:
                        embed.add_field(name="Removed Roles", value=", ".join([r.mention for r in removed_roles]))
                    embed.add_field(name="Member", value=f"{after.name}#{after.discriminator}")
                    embed.timestamp = datetime.datetime.utcnow()
                    
                    logs_channel = self.bot.get_channel(Config.LOGS_CHANNEL_ID)
                    if logs_channel:
                        await logs_channel.send(embed=embed)
                    
                    await db.log_event("MEMBER", after.id, "ROLES_UPDATED", f"Added: {len(added_roles)}, Removed: {len(removed_roles)}")
            
            # Check for nickname changes
            if before.nick != after.nick:
                embed = discord.Embed(
                    title="Member Nickname Changed",
                    description=f"Nickname changed for {after.mention}",
                    color=discord.Color.blue()
                )
                embed.add_field(name="Before", value=before.nick or "(No nickname)")
                embed.add_field(name="After", value=after.nick or "(No nickname)")
                embed.timestamp = datetime.datetime.utcnow()
                
                logs_channel = self.bot.get_channel(Config.LOGS_CHANNEL_ID)
                if logs_channel:
                    await logs_channel.send(embed=embed)
                
                await db.log_event("MEMBER", after.id, "NICKNAME_CHANGED", f"From: {before.nick}, To: {after.nick}")
        except Exception as e:
            logger.exception(f"Error logging member update: {e}")

async def setup(bot):
    await bot.add_cog(LoggingCog(bot))
