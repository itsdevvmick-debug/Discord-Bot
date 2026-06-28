"""
Ticket Cog - Handles ticket system with dropdown menus and AI integration
"""
import discord
from discord import app_commands
from discord.ext import commands
from config import Config
from database import db
import random
import string
import re
import io
import logging
from typing import Optional
from datetime import datetime
import typing

logger = logging.getLogger(__name__)

# OpenAI is optional; avoid crashing if package is missing
try:
    import openai
    if getattr(Config, "OPENAI_API_KEY", None):
        openai.api_key = Config.OPENAI_API_KEY
    else:
        openai = None
except Exception:
    openai = None

# In-memory state for marketing-ticket flows
# Channels where the user has accepted requirements and should now submit their partner ad
accepted_partner_submission_channels: set[int] = set()
# Simple conversation history per channel for AI Q&A (list of dicts for ChatCompletion)
ai_conversations: dict[int, list] = {}
# Pending partner submissions keyed by ticket channel id
pending_partner_submissions: dict[int, dict] = {}

class TicketTypeSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Support Ticket", value="support"),
            discord.SelectOption(label="Marketing Ticket", value="marketing"),
            discord.SelectOption(label="Management Ticket", value="management"),
        ]
        super().__init__(placeholder="Select ticket type...", options=options)
    
    async def callback(self, interaction: discord.Interaction):
        ticket_type = self.values[0]
        await create_ticket(interaction, ticket_type)

class TicketTypeView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(TicketTypeSelect())


async def save_transcript(channel: discord.TextChannel, ticket_id: str):
    """Collect channel history and post transcript to logs channel."""
    msgs = [m async for m in channel.history(limit=2000, oldest_first=True)]
    buf = io.StringIO()
    for m in msgs:
        timestamp = m.created_at.isoformat()
        author = f"{m.author}"
        content = m.content
        buf.write(f"[{timestamp}] {author}: {content}\n")
        for a in m.attachments:
            buf.write(f"[{timestamp}] {author} ATTACHMENT: {a.url}\n")

    buf.seek(0)
    # Prefer explicit ticket logs config, fallback to general logs channel
    ticket_logs_id = getattr(Config, "TICKET_LOGS_CHANNEL_ID", None) or getattr(Config, "LOGS_CHANNEL_ID", None)
    logs_channel = channel.guild.get_channel(int(ticket_logs_id)) if ticket_logs_id else None
    if logs_channel:
        file = discord.File(fp=io.BytesIO(buf.getvalue().encode("utf-8")), filename=f"transcript-{ticket_id}.txt")
        embed = discord.Embed(title="Ticket Transcript", description=f"Transcript for ticket {ticket_id}", color=0xE0E0E0)
        embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot")
        await logs_channel.send(embed=embed, file=file)
    else:
        logger.warning("Ticket logs channel not found; transcript not posted.")

async def create_ticket(interaction: discord.Interaction, ticket_type: str):
    """Create a new ticket"""
    if not interaction.guild:
        await interaction.response.send_message("Tickets can only be created in a server.", ephemeral=True)
        return

    if not interaction.response.is_done():
        await interaction.response.defer(ephemeral=True, thinking=True)
    
    # Generate ticket ID
    ticket_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    # Get category and permissions
    def slugify(name: str) -> str:
        name = name.lower()
        name = re.sub(r"[^a-z0-9 -]", "", name)
        name = name.replace(" ", "-")
        return name[:90]

    if ticket_type == "support":
        category_id = Config.SUPPORT_CATEGORY_ID
        channel_name = f"support-{ticket_id.lower()}"
        role_id = getattr(Config, "SUPPORT_ROLE_ID", getattr(Config, "MODERATOR_ROLE_ID", None))
    elif ticket_type == "marketing":
        category_id = Config.MARKETING_CATEGORY_ID
        # use username in channel name for marketing tickets
        user_slug = slugify(interaction.user.name)
        channel_name = f"marketing-{user_slug}-{ticket_id.lower()}"
        role_id = getattr(Config, "MARKETING_ROLE_ID", None)
    else:
        category_id = Config.MANAGEMENT_CATEGORY_ID
        channel_name = f"management-{ticket_id.lower()}"
        role_id = getattr(Config, "MANAGEMENT_ROLE_ID", getattr(Config, "TEAM_LEADER_ROLE_ID", None))
    
    category = interaction.guild.get_channel(category_id)
    
    # Create ticket channel
    overwrites = {
        interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
        interaction.guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }
    
    # Add role to overwrites if it exists
    role = discord.utils.get(interaction.guild.roles, id=role_id)
    if role:
        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=True)
    
    # Create the channel inside the category if possible, otherwise create at guild level
    if category and isinstance(category, discord.CategoryChannel):
        channel = await category.create_text_channel(channel_name, overwrites=overwrites)
    else:
        channel = await interaction.guild.create_text_channel(channel_name, overwrites=overwrites)
    
    # Create ticket embed
    embed = discord.Embed(
        title=f"{ticket_type.capitalize()} Ticket",
        description=f"Ticket: {ticket_id}",
        color=0xE0E0E0
    )
    embed.add_field(name="Creator", value=interaction.user.mention, inline=False)
    embed.add_field(name="Status", value="Open", inline=True)
    embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot | Private channel")
    
    # Send initial message with buttons
    view = TicketControlView(ticket_id, ticket_type)
    await channel.send(embed=embed, view=view)

    # Welcome message with role mention
    welcome_msg = f"Hello, thank you for making a ticket at {Config.BRAND_SHORT_NAME}!"
    if role:
        welcome_msg += f"\n{role.mention}"

    await channel.send(welcome_msg)

    # AI Marketing Integration: always send greeting; use OpenAI when available, fallback otherwise
    if ticket_type == "marketing":
        # Always send the project's required partnership message exactly
        requirements = (
            f"Hello! Thank you for making a ticket at {Config.BRAND_NAME}.\n"
            "Here are our partner requirements:\n\n"
            f"## {Config.BRAND_NAME} - Partner requirements\n\n"
            "*Member requirements:*\n"
            "We do not have fixed member requirements at the moment because we are testing our marketing flow.\n\n"
            "*Other requirements:*\n"
            "- Your server is Roblox-related, blacklist-related, or a development shop. Giveaway-only servers are not allowed.\n"
            "- If you leave the server, your ad can be removed.\n"
            "- The server owner must not be on our blacklist.\n"
            "- Your server must follow the Discord Terms of Service.\n\n"
            "**Be aware:**\n"
            "We do not do pings.\n\n"
            "When you accept, please type: accept\nWhen you decline, please type: decline"
        )
        await channel.send(requirements)

        # If OpenAI is enabled, initialize a conversation context for this channel
        if openai:
            sys_msg = {
                "role": "system",
                "content": (
                    f"You are a professional marketing coordinator for {Config.BRAND_NAME} ({Config.BUSINESS_DESCRIPTION}). "
                    "Answer user questions about partnership requirements and help them prepare a partnership ad. "
                    "Be concise and professional. If the user asks to generate or improve their partnership message, produce a short ad they can post."
                )
            }
            ai_conversations[channel.id] = [sys_msg]
    
    # Store ticket in database
    try:
        await db.execute(
            """
            INSERT INTO tickets (ticket_id, channel_id, user_id, ticket_type, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [ticket_id, channel.id, interaction.user.id, ticket_type, "open", datetime.utcnow()],
        )
    except Exception as exc:
        logger.exception(f"Error storing ticket {ticket_id}: {exc}")

    await db.log_event("TICKET", interaction.user.id, "TICKET_CREATED", f"Type: {ticket_type}")
    
    await interaction.followup.send(f"Ticket created: {channel.mention}", ephemeral=True)

class TicketControlView(discord.ui.View):
    def __init__(self, ticket_id: str, ticket_type: str):
        super().__init__()
        self.ticket_id = ticket_id
        self.ticket_type = ticket_type
    
    @discord.ui.button(label="Claim", style=discord.ButtonStyle.success)
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Claim the ticket"""
        await interaction.response.send_message(f"Ticket claimed by {interaction.user.mention}")
        await db.log_event("TICKET", interaction.user.id, "TICKET_CLAIMED", f"ID: {self.ticket_id}")

    @discord.ui.button(label="Delete", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Delete the ticket channel (saves transcript first)"""
        channel = interaction.channel
        # permission check
        has_perm = interaction.user.guild_permissions.manage_channels
        ceo_role = discord.utils.get(interaction.guild.roles, id=Config.CEO_ROLE_ID)
        if ceo_role and ceo_role in interaction.user.roles:
            has_perm = True
        if not has_perm:
            await interaction.response.send_message("You don't have permission to delete this ticket.", ephemeral=True)
            return

        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            await save_transcript(channel, self.ticket_id)
        except Exception as e:
            logger.exception("Error saving transcript before delete")

        try:
            await channel.delete(reason=f"Ticket deleted by {interaction.user}")
        except Exception as e:
            await interaction.followup.send(f"Failed to delete channel: {e}", ephemeral=True)


class MarketingApprovalView(discord.ui.View):
    def __init__(self, ticket_id: str):
        super().__init__()
        self.ticket_id = ticket_id

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only marketing role can approve
        marketing_role = discord.utils.get(interaction.guild.roles, id=Config.MARKETING_ROLE_ID)
        if not marketing_role or marketing_role not in interaction.user.roles:
            await interaction.response.send_message("Only the marketing team can approve.", ephemeral=True)
            return
        channel = interaction.channel

        # Get pending submission for this ticket channel
        submission = pending_partner_submissions.get(channel.id)
        if not submission:
            await interaction.response.send_message("No pending submission found for this ticket.", ephemeral=True)
            return

        # Set status to awaiting proof and prompt the submitter to post proof
        submission['status'] = 'awaiting_proof'

        ad_preview = submission.get('content')[:1500]
        try:
            await channel.send(
                f"Server follows our regulations.\nHere is our ad:\n\n{ad_preview}\n\nPlease send proof now that you have posted our partnership ad:")
        except Exception:
            await channel.send("Please send proof now that you have posted our partnership ad:")

        await db.log_event("PARTNER", interaction.user.id, "MARKETING_APPROVED_PENDING_PROOF", f"Ticket {self.ticket_id}")
        await interaction.response.send_message("Marked as approved — awaiting proof from submitter.", ephemeral=True)


class ProofApprovalView(discord.ui.View):
    def __init__(self, ticket_id: str):
        super().__init__()
        self.ticket_id = ticket_id

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success)
    async def yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only marketing role can confirm
        marketing_role = discord.utils.get(interaction.guild.roles, id=Config.MARKETING_ROLE_ID)
        if not marketing_role or marketing_role not in interaction.user.roles:
            await interaction.response.send_message("Only the marketing team can confirm.", ephemeral=True)
            return

        channel = interaction.channel
        submission = pending_partner_submissions.get(channel.id)
        if not submission:
            await interaction.response.send_message("No submission found.", ephemeral=True)
            return

        # Post to partners channel as plain message (no embed, no robux/member counts)
        partners_channel = interaction.guild.get_channel(getattr(Config, "PARTNERS_CHANNEL_ID", None) or Config.PARTNERS_CHANNEL_ID)
        if partners_channel:
            try:
                await partners_channel.send(submission.get('content'))
            except Exception:
                pass
        else:
            await channel.send("Partners channel not configured; posting failed.")

        submission['posted'] = True
        try:
            await db.add_partner(submission.get('server_name'), submission.get('robux', 0), submission.get('members', 0), submission.get('content'), submission.get('author_id'))
        except Exception:
            pass

        await db.log_event('PARTNER', interaction.user.id, 'POSTED', f"Ticket {self.ticket_id}")

        # Notify submitter to close or keep open
        try:
            ch = channel
            await ch.send("Partner posted. To close this ticket type `close`, to leave it open type `open`.")
        except Exception:
            pass

        await interaction.response.send_message("Partner posted and submitter notified.", ephemeral=True)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def no(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketing_role = discord.utils.get(interaction.guild.roles, id=Config.MARKETING_ROLE_ID)
        if not marketing_role or marketing_role not in interaction.user.roles:
            await interaction.response.send_message("Only the marketing team can reject.", ephemeral=True)
            return

        channel = interaction.channel
        sub = pending_partner_submissions.pop(channel.id, None)
        if sub:
            try:
                user = await channel.guild.fetch_member(sub.get('author_id'))
                await user.send(f"Your partnership submission in {channel.name} was rejected after proof review.")
            except Exception:
                pass

        await db.log_event('PARTNER', interaction.user.id, 'PROOF_REJECTED', f"Ticket {self.ticket_id}")
        await interaction.response.send_message("Submission rejected and submitter notified.", ephemeral=True)


    @discord.ui.button(label="Reject", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        marketing_role = discord.utils.get(interaction.guild.roles, id=Config.MARKETING_ROLE_ID)
        if not marketing_role or marketing_role not in interaction.user.roles:
            await interaction.response.send_message("Only the marketing team can reject.", ephemeral=True)
            return

        channel = interaction.channel
        # remove any pending submission for this ticket
        submission = pending_partner_submissions.pop(channel.id, None)
        await channel.send(f"Marketing has rejected this partnership request. Please review the requirements and try again.")
        if submission:
            # notify the submitter privately if possible
            try:
                user = await interaction.guild.fetch_member(submission.get('author_id'))
                await user.send(f"Your partnership submission in {channel.name} was rejected by the marketing team.")
            except Exception:
                pass

        await db.log_event("PARTNER", interaction.user.id, "MARKETING_REJECTED", f"Ticket {self.ticket_id}")
        await interaction.response.send_message("Rejected.", ephemeral=True)
    
    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Close the ticket immediately (no reason)"""
        channel = interaction.channel
        try:
            # rename and make read-only
            await channel.edit(name=f"closed-{self.ticket_id}")
            await channel.set_permissions(interaction.guild.default_role, send_messages=False, view_channel=False)
            await channel.set_permissions(interaction.guild.me, send_messages=True, view_channel=True)
            embed = discord.Embed(title="Ticket Closed", description="Closed without reason", color=discord.Color.green())
            await channel.send(embed=embed)
            await db.execute(
                "UPDATE tickets SET status = 'closed', closed_at = ?, close_reason = ? WHERE ticket_id = ?",
                [datetime.utcnow(), "Closed without reason", self.ticket_id],
            )
            await db.log_event("TICKET", interaction.user.id, "TICKET_CLOSED", "Closed without reason")
            await interaction.response.send_message("Ticket closed.", ephemeral=True)
        except Exception as e:
            logger.exception("Error closing ticket")
            await interaction.response.send_message(f"Error closing ticket: {e}", ephemeral=True)

    @discord.ui.button(label="Close (With reason)", style=discord.ButtonStyle.danger)
    async def close_with_reason(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Open modal to provide a reason when closing"""
        modal = CloseTicketModal(self.ticket_id)
        await interaction.response.send_modal(modal)
    
    @discord.ui.button(label="Add User", style=discord.ButtonStyle.secondary)
    async def add_user(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Add a user to the ticket"""
        await interaction.response.send_message("Mention the user to add them to this ticket", ephemeral=True)
    
    @discord.ui.button(label="Transcript", style=discord.ButtonStyle.secondary)
    async def transcript(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Get ticket transcript"""
        await interaction.response.defer(thinking=True, ephemeral=True)
        try:
            await save_transcript(interaction.channel, self.ticket_id)
            await interaction.followup.send("Transcript posted to ticket logs.", ephemeral=True)
        except Exception as e:
            logger.exception("Error creating transcript")
            await interaction.followup.send(f"Error creating transcript: {e}", ephemeral=True)

class CloseTicketModal(discord.ui.Modal, title="Close Ticket"):
    def __init__(self, ticket_id: str):
        super().__init__()
        self.ticket_id = ticket_id

    reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, required=False)

    async def on_submit(self, interaction: discord.Interaction):
        channel = interaction.channel
        reason_text = self.reason.value or "No reason provided"
        embed = discord.Embed(
            title="Ticket Closed",
            description=f"Reason: {reason_text}",
            color=discord.Color.green()
        )
        try:
            # Save transcript then close
            await save_transcript(channel, self.ticket_id)
            await channel.send(embed=embed)
            await channel.edit(name=f"closed-{self.ticket_id}")
            await channel.set_permissions(interaction.guild.default_role, send_messages=False, view_channel=False)
            await channel.set_permissions(interaction.guild.me, send_messages=True, view_channel=True)
            await db.execute(
                "UPDATE tickets SET status = 'closed', closed_at = ?, close_reason = ? WHERE ticket_id = ?",
                [datetime.utcnow(), reason_text, self.ticket_id],
            )
            await db.log_event("TICKET", interaction.user.id, "TICKET_CLOSED", reason_text)
            await interaction.response.send_message("Ticket closed with reason.", ephemeral=True)
        except Exception as e:
            logger.exception(f"Error during close modal: {e}")
            await interaction.response.send_message(f"Error closing ticket: {e}", ephemeral=True)

class TicketCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
    
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Listen for 'accept' in marketing tickets"""
        
        if message.author.bot:
            return

        if not message.guild or not hasattr(message.channel, "name"):
            return
        
        # Check if in a marketing ticket channel
        if not message.channel.name.startswith("marketing-"):
            return
        # First: detect proof messages when marketing previously approved and proof is awaited
        submission = pending_partner_submissions.get(message.channel.id)
        if submission and submission.get('status') == 'awaiting_proof' and message.author.id == submission.get('author_id'):
            # basic proof detection: attachments or http(s) link
            has_proof = False
            if message.attachments:
                has_proof = True
            if not has_proof and re.search(r"https?://", message.content or ""):
                has_proof = True

            if has_proof:
                submission['proof'] = {
                    'content': message.content,
                    'attachments': [a.url for a in message.attachments]
                }
                submission['status'] = 'proof_provided'

                # Notify marketing with proof and ask for confirmation
                marketing_role = discord.utils.get(message.guild.roles, id=Config.MARKETING_ROLE_ID)
                proof_embed = discord.Embed(title="Proof Submitted", description=f"Submitter {message.author.mention} provided proof.", color=discord.Color.gold())
                proof_embed.add_field(name="Submission Preview", value=submission.get('content')[:1024], inline=False)
                if submission['proof']['attachments']:
                    proof_embed.add_field(name="Attachments", value='\n'.join(submission['proof']['attachments'][:5]), inline=False)
                if submission['proof']['content']:
                    proof_embed.add_field(name="Proof Message", value=submission['proof']['content'][:1024], inline=False)

                view = ProofApprovalView(ticket_id=message.channel.name.split('-')[-1] if '-' in message.channel.name else 'unknown')
                if marketing_role:
                    await message.channel.send(f"{marketing_role.mention} - Is the ad posted?", embed=proof_embed, view=view)
                else:
                    await message.channel.send(embed=proof_embed, view=view)
                await db.log_event('PARTNER', message.author.id, 'PROOF_SUBMITTED', f"Channel: {message.channel.id}")
                return

        # After posting, submitter can close or reopen the ticket
        if message.content.strip().lower() == "close":
            submission = pending_partner_submissions.get(message.channel.id)
            if submission and submission.get('posted') and message.author.id == submission.get('author_id'):
                try:
                    await message.channel.edit(name=f"closed-{message.channel.name.split('-')[-1]}")
                    await message.channel.set_permissions(message.guild.default_role, send_messages=False, view_channel=False)
                    await message.channel.set_permissions(message.guild.me, send_messages=True, view_channel=True)
                    embed = discord.Embed(title="Ticket Closed", description="Closed after partnership posting.", color=0xE0E0E0)
                    embed.set_footer(text=f"{Config.BRAND_SHORT_NAME} Bot")
                    await message.channel.send(embed=embed)
                    ticket_id = message.channel.name.split('-')[-1]
                    await db.execute(
                        "UPDATE tickets SET status = 'closed', closed_at = ?, close_reason = ? WHERE ticket_id = ?",
                        [datetime.utcnow(), "Closed after partner posted", ticket_id],
                    )
                    await db.log_event("TICKET", message.author.id, "TICKET_CLOSED", "Closed after partner posted")
                except Exception as e:
                    logger.exception(f"Error closing ticket after post")

        if message.content.strip().lower() == "open":
            submission = pending_partner_submissions.get(message.channel.id)
            if submission and submission.get('posted') and message.author.id == submission.get('author_id'):
                await message.channel.send("Ticket will remain open.")
                await db.log_event("TICKET", message.author.id, "TICKET_LEFT_OPEN", "Left open after partner posted")
                return
        
        if message.content.strip().lower() == "accept":
            embed = discord.Embed(
                title="Requirements Accepted",
                description="Requirements accepted! Please now send your partnership proposal/ad below.",
                color=discord.Color.green()
            )
            await message.channel.send(embed=embed)

            # mark this channel as awaiting the user's partnership submission
            accepted_partner_submission_channels.add(message.channel.id)

            await db.log_event("TICKET", message.author.id, "ACCEPTED_REQUIREMENTS", "")
            return

        if message.content.strip().lower() == "decline":
            await message.channel.send("You have declined the partnership requirements. If you change your mind, type accept.")
            await db.log_event("TICKET", message.author.id, "DECLINED_REQUIREMENTS", "")
            return

        # If channel is awaiting a partner submission, treat the next non-empty message as the ad
        if message.channel.id in accepted_partner_submission_channels:
            content = message.content.strip()
            if len(content) < 10:
                await message.channel.send("Submission too short — please provide your full partnership ad.")
                return

            # queue pending submission for marketing review
            pending_partner_submissions[message.channel.id] = {
                "author_id": message.author.id,
                "author_name": message.author.display_name,
                "content": content,
                "server_name": message.author.display_name,
                "robux": 0,
                "members": 0,
                "status": "queued",
                "proof": None,
                "posted": False
            }

            # send review embed and buttons in the ticket channel, ping marketing team
            marketing_role = discord.utils.get(message.guild.roles, id=Config.MARKETING_ROLE_ID)
            review_embed = discord.Embed(
                title="Partnership Submission Ready for Review",
                description=f"A partnership submission was posted by {message.author.mention} in this ticket.",
                color=discord.Color.gold()
            )
            review_embed.add_field(name="Submission Preview", value=content[:1024], inline=False)
            review_embed.add_field(name="Submitted in", value=message.channel.mention)

            view = MarketingApprovalView(ticket_id=message.channel.name.split('-')[-1] if '-' in message.channel.name else 'unknown')
            if marketing_role:
                await message.channel.send(f"{marketing_role.mention} - Does this server follow our regulations?", embed=review_embed, view=view)
            else:
                await message.channel.send(embed=review_embed, view=view)

            await db.log_event("PARTNER", message.author.id, "SUBMISSION_QUEUED", f"Channel: {message.channel.id}")
            accepted_partner_submission_channels.discard(message.channel.id)
            return
    
    @app_commands.command(name="panel", description="Create ticket selection panel")
    async def panel(self, interaction: discord.Interaction):
        """Create main ticket panel with dropdown menu"""
        
        # Check if user is CEO (owner has CEO role)
        ceo_role = discord.utils.get(interaction.guild.roles, id=Config.CEO_ROLE_ID)
        if not ceo_role or ceo_role not in interaction.user.roles:
            await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
            return
        
        try:
            embed = discord.Embed(
                title="TICKET SYSTEM",
                description="Select a ticket type from the dropdown menu below",
                color=discord.Color.blue()
            )
            embed.add_field(name="Support", value="Create a support ticket for general help")
            embed.add_field(name="Marketing", value="Submit a partnership request")
            embed.add_field(name="Management", value="Management related issues")

            view = TicketTypeView()
            await interaction.response.send_message(embed=embed, view=view)
            await db.log_event("TICKET", interaction.user.id, "PANEL_CREATED", "Main ticket panel")
        except Exception as e:
            await interaction.response.send_message(f"Error creating panel: {str(e)}", ephemeral=True)
            try:
                await interaction.response.send_message(f"Error creating panel: {str(e)}", ephemeral=True)
            except Exception:
                await interaction.followup.send(f"Error creating panel: {str(e)}", ephemeral=True)

    @app_commands.command(name="rename", description="Rename the current ticket channel")
    @app_commands.describe(new_name="New channel name")
    async def rename(self, interaction: discord.Interaction, new_name: str):
        channel = interaction.channel
        if not channel.name.startswith(("support-","marketing-","management-","closed-")):
            await interaction.response.send_message("This command can only be used inside a ticket channel.", ephemeral=True)
            return

        # permission check
        has_perm = interaction.user.guild_permissions.manage_channels
        ceo_role = discord.utils.get(interaction.guild.roles, id=Config.CEO_ROLE_ID)
        if ceo_role and ceo_role in interaction.user.roles:
            has_perm = True

        if not has_perm:
            await interaction.response.send_message("You don't have permission to rename this ticket.", ephemeral=True)
            return

        # sanitize new name
        slug = re.sub(r"[^a-z0-9 -]", "", new_name.lower()).replace(" ", "-")[:90]
        try:
            await channel.edit(name=slug)
            await interaction.response.send_message(f"Channel renamed to {slug}", ephemeral=True)
            await db.log_event("TICKET", interaction.user.id, "RENAME", f"Renamed to {slug}")
        except Exception as e:
            await interaction.response.send_message(f"Error renaming channel: {e}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(TicketCog(bot))

