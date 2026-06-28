"""
Marketing Period Cog - Handles marketing periods and team statistics with live updates
"""
import discord
from discord import app_commands
from discord.ext import commands
from config import Config
from database import db
import datetime
import logging

logger = logging.getLogger(__name__)

class MarketingPeriodCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.current_period = None
        self.period_message = None
    
    def has_team_leader_role(self, interaction: discord.Interaction) -> bool:
        """Check if user is team leader"""
        leader_role = discord.utils.get(interaction.guild.roles, id=Config.TEAM_LEADER_ROLE_ID)
        return leader_role in interaction.user.roles if leader_role else False
    
    async def get_period_stats(self):
        """Get current period statistics from database"""
        try:
            # Get partner count
            result = await db.fetch_one("SELECT COUNT(*) FROM partners WHERE status = 'approved'")
            partner_count = result[0] if result else 0
            
            # Get total robux from active period
            result = await db.fetch_one("SELECT SUM(robux_reward) FROM partners WHERE status = 'approved'")
            total_robux = result[0] if result and result[0] else 0
            
            return partner_count, total_robux
        except Exception as e:
            logging.exception("Error getting period stats")
            return 0, 0
    
    @app_commands.command(name="startperiod", description="Start a new marketing period")
    @app_commands.describe(
        month="Month name (e.g., 'February 2026')",
        remarks="Optional remarks/goals for this period"
    )
    async def startperiod(self, interaction: discord.Interaction, month: str, remarks: str = None):
        """Start a new marketing period"""
        
        if not self.has_team_leader_role(interaction):
            await interaction.response.send_message("Only team leaders can start periods!", ephemeral=True)
            return
        
        self.current_period = {
            "name": month,
            "remarks": remarks or "No specific remarks",
            "start_time": datetime.datetime.utcnow()
        }
        
        # Send announcement
        announce_channel = interaction.guild.get_channel(Config.MARKETING_ANNOUNCEMENTS_CHANNEL_ID)
        if announce_channel:
            embed = discord.Embed(
                title="Marketing Period Started",
                description=f"Period: {month}",
                color=0xE0E0E0
            )
            
            # Get all marketing role members
            marketing_role = discord.utils.get(interaction.guild.roles, id=Config.MARKETING_ROLE_ID)
            if marketing_role:
                marketers = [m.mention for m in marketing_role.members]
                embed.add_field(
                    name="Team Members",
                    value="\n".join(marketers) if marketers else "No team members assigned",
                    inline=False
                )
            
            if remarks:
                embed.add_field(name="Notes", value=remarks, inline=False)
            
            embed.add_field(name="Partnerships", value="0", inline=True)
            embed.add_field(name="Total Reward", value="R$ 0", inline=True)
            embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot | Started by {interaction.user.name}")
            
            self.period_message = await announce_channel.send(embed=embed)
        
        await interaction.response.send_message(f"Marketing period {month} started!", ephemeral=True)
        await db.log_event("MARKETING_PERIOD", interaction.user.id, "PERIOD_STARTED", f"Started {month}: {remarks or 'No remarks'}")
    
    @app_commands.command(name="updateperiod", description="Update current period statistics")
    async def updateperiod(self, interaction: discord.Interaction):
        """Update marketing period stats in message"""
        
        if not self.has_team_leader_role(interaction):
            await interaction.response.send_message("Only team leaders can update periods!", ephemeral=True)
            return
        
        if not self.current_period or not self.period_message:
            await interaction.response.send_message("No active period to update!", ephemeral=True)
            return
        
        try:
            # Get fresh stats
            partner_count, total_robux = await self.get_period_stats()
            
            # Update original message
            embed = discord.Embed(
                title="Marketing Period Active",
                description=f"Period: {self.current_period['name']}",
                color=0xE0E0E0
            )
            
            marketing_role = discord.utils.get(interaction.guild.roles, id=Config.MARKETING_ROLE_ID)
            if marketing_role:
                marketers = [m.mention for m in marketing_role.members]
                embed.add_field(
                    name="Team Members",
                    value="\n".join(marketers) if marketers else "No team members assigned",
                    inline=False
                )
            
            if self.current_period.get("remarks"):
                embed.add_field(name="Notes", value=self.current_period["remarks"], inline=False)
            
            embed.add_field(name="Partnerships", value=str(partner_count), inline=True)
            embed.add_field(name="Total Reward", value=f"R$ {total_robux:,}", inline=True)
            embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot | Updated by {interaction.user.name}")
            
            await self.period_message.edit(embed=embed)
            await interaction.response.send_message("Statistics updated.", ephemeral=True)
            
        except Exception as e:
            logger.exception("Error updating period")
            await interaction.response.send_message(f"Error updating period: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="endperiod", description="End the current marketing period")
    async def endperiod(self, interaction: discord.Interaction):
        """End the current marketing period"""
        
        if not self.has_team_leader_role(interaction):
            await interaction.response.send_message("Only team leaders can end periods!", ephemeral=True)
            return
        
        if not self.current_period:
            await interaction.response.send_message("No active period to end!", ephemeral=True)
            return
        
        period_name = self.current_period["name"]
        
        try:
            # Get final stats
            partner_count, total_robux = await self.get_period_stats()
            
            # Send final announcement with stats
            announce_channel = interaction.guild.get_channel(Config.MARKETING_ANNOUNCEMENTS_CHANNEL_ID)
            if announce_channel:
                embed = discord.Embed(
                    title="Marketing Period Ended",
                    description=f"Period: {period_name}",
                    color=0xE0E0E0
                )
                
                embed.add_field(name="Total Partnerships", value=str(partner_count), inline=True)
                embed.add_field(name="Total Reward", value=f"R$ {total_robux:,}", inline=True)
                
                if self.current_period.get("remarks"):
                    embed.add_field(name="Notes", value=self.current_period["remarks"], inline=False)
                
                embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot | Ended by {interaction.user.name}")
                
                await announce_channel.send(embed=embed)
            
            self.current_period = None
            self.period_message = None
            
            await interaction.response.send_message("Marketing period ended.", ephemeral=True)
            await db.log_event("MARKETING_PERIOD", interaction.user.id, "PERIOD_ENDED", 
                             f"Ended {period_name} - Partners: {partner_count}, Robux: {total_robux}")
        
        except Exception as e:
            logger.exception("Error ending period")
            await interaction.response.send_message(f"Error ending period: {str(e)}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(MarketingPeriodCog(bot))
