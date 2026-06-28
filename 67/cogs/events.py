"""
Events Cog - Handles welcome, goodbye, and member events
"""
import discord
from discord.ext import commands
from config import Config
from database import db
import datetime
import logging

logger = logging.getLogger(__name__)

class EventsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Send welcome message when member joins"""
        try:
            channel = self.bot.get_channel(Config.WELCOME_CHANNEL_ID)
            if not channel:
                return
            
            embed = discord.Embed(
                title="Welcome!",
                description=f"Welcome to {Config.BRAND_NAME}, {member.mention}!\n\nPlease read our rules and check out our channels.",
                color=0xE0E0E0
            )
            embed.add_field(name="Member Count", value=f"We now have {member.guild.member_count} members", inline=False)
            embed.add_field(name="User ID", value=member.id)
            embed.add_field(name="Joined At", value=f"<t:{int(datetime.datetime.utcnow().timestamp())}>")
            embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
            embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} • Welcome!")
            
            await channel.send(embed=embed)
            
            # Log event
            await db.log_event("MEMBER_JOIN", member.id, "JOIN", f"{member} joined the server")
        
        except Exception as e:
            logger.exception(f"Error in on_member_join: {e}")
    
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Send goodbye message when member leaves"""
        try:
            channel = self.bot.get_channel(Config.GOODBYE_CHANNEL_ID)
            if not channel:
                return
            
            embed = discord.Embed(
                title="Goodbye!",
                description=f"{member.mention} has left {Config.BRAND_NAME}.",
                color=0xE0E0E0
            )
            embed.add_field(name="Member Status", value="See you again!")
            embed.set_thumbnail(url=member.avatar.url if member.avatar else None)
            embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} • Goodbye!")
            
            await channel.send(embed=embed)
            
            # Log event
            await db.log_event("MEMBER_LEAVE", member.id, "LEAVE", f"{member} left the server")
        
        except Exception as e:
            logger.exception(f"Error in on_member_remove: {e}")
    
    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        """Log voice channel updates"""
        try:
            # Member joined a voice channel
            if before.channel is None and after.channel is not None:
                await db.log_event(
                    "VOICE",
                    member.id,
                    "VOICE_JOIN",
                    f"{member} joined voice channel {after.channel.name}"
                )
            
            # Member left a voice channel
            elif before.channel is not None and after.channel is None:
                await db.log_event(
                    "VOICE",
                    member.id,
                    "VOICE_LEAVE",
                    f"{member} left voice channel {before.channel.name}"
                )
            
            # Member switched voice channels
            elif before.channel != after.channel:
                await db.log_event(
                    "VOICE",
                    member.id,
                    "VOICE_SWITCH",
                    f"{member} switched from {before.channel.name} to {after.channel.name}"
                )
        
        except Exception as e:
            logger.exception(f"Error in on_voice_state_update: {e}")

async def setup(bot):
    await bot.add_cog(EventsCog(bot))
