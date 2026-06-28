"""
Utility Cog - Misc commands like poll, game, products, announcements
"""
import discord
from discord import app_commands
from discord.ext import commands
from config import Config
from database import db
from typing import Optional
import random
import logging

logger = logging.getLogger(__name__)

class UtilityCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @app_commands.command(name="poll", description="Create a poll")
    @app_commands.describe(question="The poll question", option1="First option", option2="Second option", option3="Third option (optional)")
    async def poll(self, interaction: discord.Interaction, question: str, option1: str, option2: str, option3: Optional[str] = None):
        """Create a poll"""
        
        embed = discord.Embed(
            title="POLL",
            description=question,
            color=discord.Color.blue()
        )
        
        options = [option1, option2]
        if option3:
            options.append(option3)
        
        option_emojis = ["1️⃣", "2️⃣", "3️⃣"]
        
        for i, option in enumerate(options):
            embed.add_field(name=f"{option_emojis[i]} {option}", value="0 votes", inline=False)
        
        await interaction.response.send_message(embed=embed)
        message = await interaction.original_response()
        
        for i in range(len(options)):
            await message.add_reaction(option_emojis[i])
        
        await db.log_event("POLL", interaction.user.id, "POLL_CREATED", question)
    
    @app_commands.command(name="dice", description="Roll a dice")
    @app_commands.describe(sides="Number of sides (default 6)")
    async def dice(self, interaction: discord.Interaction, sides: int = 6):
        """Roll a dice"""
        
        if sides < 1:
            await interaction.response.send_message("Dice must have at least 1 side!", ephemeral=True)
            return
        
        result = random.randint(1, sides)
        
        embed = discord.Embed(
            title="DICE ROLL",
            description=f"You rolled a **{result}** on a d{sides}",
            color=discord.Color.purple()
        )
        
        await interaction.response.send_message(embed=embed)
        await db.log_event("GAME", interaction.user.id, "DICE_ROLLED", f"Rolled d{sides}: {result}")
    
    @app_commands.command(name="8ball", description="Ask the magic 8 ball a question")
    @app_commands.describe(question="Your question")
    async def eightball(self, interaction: discord.Interaction, question: str):
        """Magic 8 ball"""
        
        responses = [
            "Yes, definitely!", "No, absolutely not.", "Maybe...", "Ask again later.",
            "Outlook good!", "Very doubtful.", "Concentrate and ask again.", "Don't bet on it.",
            "It is certain.", "Outlook not so good.", "Better not tell you now.", "Most likely.",
            "Signs point to yes.", "Cannot predict now.", "Very likely.", "My sources say no."
        ]
        
        response = random.choice(responses)
        
        embed = discord.Embed(
            title="MAGIC 8 BALL",
            description=f"**Q:** {question}\n\n**A:** {response}",
            color=discord.Color.dark_purple()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="flip", description="Flip a coin")
    async def flip(self, interaction: discord.Interaction):
        """Flip a coin"""
        
        result = random.choice(["Heads", "Tails"])
        
        embed = discord.Embed(
            title="COIN FLIP",
            description=f"The coin landed on **{result}**",
            color=discord.Color.gold()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="startgame", description="Start a number guessing game")
    @app_commands.describe(min_number="Minimum number", max_number="Maximum number")
    async def startgame(self, interaction: discord.Interaction, min_number: int, max_number: int):
        """Start a number guessing game"""
        
        if min_number >= max_number:
            await interaction.response.send_message("Min must be less than max!", ephemeral=True)
            return
        
        secret_number = random.randint(min_number, max_number)
        
        embed = discord.Embed(
            title="NUMBER GUESSING GAME",
            description=f"Guess a number between {min_number} and {max_number}",
            color=discord.Color.purple()
        )
        
        await interaction.response.send_message(embed=embed)
        await db.log_event("GAME", interaction.user.id, "GAME_STARTED", f"{min_number}-{max_number}")
    
    @app_commands.command(name="addproduct", description="Add a product to the shop")
    @app_commands.describe(name="Product name", price="Product price in Robux", description="Product description")
    async def addproduct(self, interaction: discord.Interaction, name: str, price: int, description: str):
        """Add a product to the shop"""
        
        embed = discord.Embed(
            title=f"{name}",
            description=description,
            color=discord.Color.green()
        )
        embed.add_field(name="Price", value=f"R$ {price:,}")
        embed.set_footer(text="Available for purchase!")
        
        # Post to products channel if available
        products_channel = interaction.guild.get_channel(Config.PRODUCTS_FORUM_CHANNEL_ID)
        if products_channel:
            if isinstance(products_channel, discord.ForumChannel):
                await products_channel.create_thread(name=name[:100], embed=embed)
            else:
                await products_channel.send(embed=embed)
            await interaction.response.send_message(f"Product posted to {products_channel.mention}!", ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed)
        
        await db.log_event("PRODUCT", interaction.user.id, "PRODUCT_ADDED", name)
    
    @app_commands.command(name="announcement", description="Post an announcement (CEO/COO only)")
    @app_commands.describe(title="Announcement title", message="Announcement message")
    async def announcement(self, interaction: discord.Interaction, title: str, message: str):
        """Post an announcement"""
        
        # Check if user is CEO or COO
        ceo_role = discord.utils.get(interaction.guild.roles, id=Config.CEO_ROLE_ID)
        coo_role = discord.utils.get(interaction.guild.roles, id=Config.COO_ROLE_ID)
        
        has_permission = (ceo_role and ceo_role in interaction.user.roles) or (coo_role and coo_role in interaction.user.roles)
        
        if not has_permission:
            await interaction.response.send_message("You don't have permission!", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"ANNOUNCEMENT: {title}",
            description=message,
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Announced by {interaction.user.name}")
        embed.timestamp = discord.utils.utcnow()
        
        # Send to main announcements channel
        announce_channel = interaction.guild.get_channel(Config.MAIN_ANNOUNCEMENTS_CHANNEL_ID)
        if announce_channel:
            await announce_channel.send(embed=embed)
        
        await interaction.response.send_message(f"Announcement posted!", ephemeral=True)
        await db.log_event("ANNOUNCEMENT", interaction.user.id, "ANNOUNCEMENT_POSTED", title)
    
    @app_commands.command(name="whomention", description="Mention someone to tell who they are")
    @app_commands.describe(user="User to mention")
    async def whomention(self, interaction: discord.Interaction, user: discord.User):
        """Mention and describe a user"""
        
        # Get member if possible
        try:
            member = await interaction.guild.fetch_member(user.id)
        except:
            member = None
        
        embed = discord.Embed(
            title="USER INFO",
            description=f"User: {user.mention}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Username", value=user.name)
        embed.add_field(name="ID", value=user.id)
        
        if member:
            embed.add_field(name="Joined Server", value=f"<t:{int(member.joined_at.timestamp())}>")
            embed.add_field(name="Roles", value=f"{len(member.roles)} roles")
        
        embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="place_panel", description="Place the ticket panel in any channel")
    async def place_panel(self, interaction: discord.Interaction):
        """Place ticket selection panel (renamed to avoid /panel collision)"""
        
        # Check if user is CEO
        ceo_role = discord.utils.get(interaction.guild.roles, id=Config.CEO_ROLE_ID)
        if not ceo_role or ceo_role not in interaction.user.roles:
            await interaction.response.send_message("Only CEO can use this command!", ephemeral=True)
            return
        
        try:
            await interaction.response.defer()
            
            from cogs.tickets import TicketTypeView
            
            embed = discord.Embed(
                title="TICKET SYSTEM",
                description="Select a ticket type from the dropdown menu below",
                color=discord.Color.blue()
            )
            embed.add_field(name="Support", value="Create a support ticket for general help")
            embed.add_field(name="Marketing", value="Submit a partnership request")
            embed.add_field(name="Management", value="Management related issues")
            
            view = TicketTypeView()
            await interaction.followup.send(embed=embed, view=view)
            await db.log_event("UTILITY", interaction.user.id, "PANEL_PLACED", f"Channel: {interaction.channel.id}")
        except Exception as e:
            logger.exception("Error placing panel")
            try:
                await interaction.response.send_message(f"Error placing panel: {str(e)}", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"Error placing panel: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="serverinvoke", description="Get server invite info")
    async def serverinvoke(self, interaction: discord.Interaction):
        """Get server invite info"""
        
        embed = discord.Embed(
            title="Server Information",
            description=f"Server: {interaction.guild.name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Members", value=interaction.guild.member_count, inline=True)
        embed.add_field(name="Owner", value=interaction.guild.owner.mention if interaction.guild.owner else "Unknown")
        embed.add_field(name="Channels", value=len(interaction.guild.channels), inline=True)
        embed.add_field(name="Roles", value=len(interaction.guild.roles), inline=True)
        
        if interaction.guild.icon:
            embed.set_thumbnail(url=interaction.guild.icon.url)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="ping", description="Check bot latency")
    async def ping(self, interaction: discord.Interaction):
        """Check bot ping"""
        
        latency = round(self.bot.latency * 1000)
        
        embed = discord.Embed(
            title="Pong!",
            description=f"Bot latency: **{latency}ms**",
            color=discord.Color.green() if latency < 100 else discord.Color.orange()
        )
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="avatar", description="Get user avatar")
    @app_commands.describe(user="User to get avatar")
    async def avatar(self, interaction: discord.Interaction, user: discord.User = None):
        """Get user's avatar"""
        
        user = user or interaction.user
        
        embed = discord.Embed(
            title=f"{user.name}'s Avatar",
            url=user.avatar.url if user.avatar else None,
            color=discord.Color.purple()
        )
        embed.set_image(url=user.avatar.url if user.avatar else None)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="userinfo", description="Get detailed user information")
    @app_commands.describe(user="User to get info")
    async def userinfo(self, interaction: discord.Interaction, user: discord.User = None):
        """Get detailed user info"""
        
        user = user or interaction.user
        
        try:
            member = await interaction.guild.fetch_member(user.id)
        except:
            member = None
        
        embed = discord.Embed(
            title=f"{user.name}",
            color=discord.Color.blue()
        )
        embed.add_field(name="Username", value=user.name)
        embed.add_field(name="User ID", value=f"`{user.id}`")
        embed.add_field(name="Bot", value="Yes" if user.bot else "No")
        
        if member:
            embed.add_field(name="Joined Server", value=f"<t:{int(member.joined_at.timestamp())}>")
            embed.add_field(name="Account Created", value=f"<t:{int(user.created_at.timestamp())}>")
            
            roles = [r.mention for r in member.roles if r != interaction.guild.default_role]
            if roles:
                embed.add_field(name="Roles", value=", ".join(roles[:5]), inline=False)
        
        embed.set_thumbnail(url=user.avatar.url if user.avatar else None)
        
        await interaction.response.send_message(embed=embed)
    
    @app_commands.command(name="banlist", description="View recent bans")
    async def banlist(self, interaction: discord.Interaction):
        """Show recent bans"""
        try:
            bans = [entry async for entry in interaction.guild.bans(limit=10)]
            embed = discord.Embed(
                title="Recent Bans",
                color=0xE0E0E0
            )
            
            if bans:
                for entry in bans:
                    user = entry.user
                    reason = entry.reason or "No reason"
                    embed.add_field(name=f"{user.name}#{user.discriminator}", value=f"Reason: {reason}", inline=False)
            else:
                embed.description = "No recent bans"
            
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.exception("Error fetching bans")
            await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
    
    @app_commands.command(name="help", description="Show all available commands")
    async def help_command(self, interaction: discord.Interaction):
        """Show help menu"""
        
        embed = discord.Embed(
            title=f"{Config.BRAND_NAME.upper()} BOT",
            description="All available commands for the bot",
            color=0xE0E0E0
        )
        
        embed.add_field(
            name="🎁 GIVEAWAYS",
            value="`/giveaway` - Create a giveaway with prizes and duration",
            inline=False
        )
        
        embed.add_field(
            name="⚔️ MODERATION (Moderators Only)",
            value="`/kick` - Kick member\n"
                  "`/ban` - Ban member\n"
                  "`/unban` - Unban user\n"
                  "`/mute` - Mute member\n"
                  "`/unmute` - Unmute member\n"
                  "`/purge` - Delete messages\n"
                  "`/addrole` - Add role to member\n"
                  "`/removerole` - Remove role from member\n"
                  "`/warn` - Warn a member\n"
                  "`/slowmode` - Set channel slowmode\n"
                  "`/membercount` - Show server stats\n"
                  "`/serverinfo` - Show detailed server info",
            inline=False
        )
        
        embed.add_field(
            name="🛡️ RAID PROTECTION (Moderators Only)",
            value="`/raidstatus` - Check raid detection status\n"
                  "`/lockdown` - Lock all channels\n"
                  "`/unlock` - Unlock all channels",
            inline=False
        )
        
        embed.add_field(
            name="🎫 TICKET SYSTEM (Everyone)",
            value="`/panel` - Place ticket dropdown panel (CEO only)\n"
                  "Then select from: Support, Marketing, Management",
            inline=False
        )
        
        embed.add_field(
            name="🤝 PARTNERS (Marketing Role)",
            value="`/partner` - Submit partnership request\n"
                  "`/partnerlogs` - View partner history",
            inline=False
        )
        
        embed.add_field(
            name="📊 MARKETING PERIODS (Team Leaders Only)",
            value="`/startperiod` - Start period with remarks\n"
                  "`/endperiod` - End period with live stats",
            inline=False
        )
        
        embed.add_field(
            name="🎮 GAMES & FUN",
            value="`/poll` - Create a poll\n"
                  "`/dice` - Roll a dice\n"
                  "`/8ball` - Ask magic 8 ball\n"
                  "`/flip` - Flip a coin\n"
                  "`/startgame` - Number guessing game",
            inline=False
        )
        
        embed.add_field(
            name="ℹ️ UTILITIES & INFO",
            value="`/addproduct` - Add product to shop\n"
                  "`/announcement` - Post announcement (CEO/COO)\n"
                  "`/banlist` - View recent bans\n"
                  "`/whomention` - Get user info\n"
                  "`/serverinvoke` - Server information\n"
                  "`/ping` - Check bot latency\n"
                  "`/avatar` - Get user avatar\n"
                  "`/userinfo` - Get detailed user info\n"
                  "`/help` - This command",
            inline=False
        )
        
        embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot • Use / to start any command")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(UtilityCog(bot))
