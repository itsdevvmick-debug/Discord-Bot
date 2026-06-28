import asyncio
import logging
import os
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

import webserver
from config import Config
from database import db


load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(
    command_prefix=Config.BOT_PREFIX,
    intents=intents,
    help_command=None,
)


@bot.event
async def on_ready():
    """Run when the Discord gateway is ready."""
    logger.info("Bot logged in as %s", bot.user)
    logger.info("Bot is ready. Connected to %s guild(s)", len(bot.guilds))

    try:
        if Config.SERVER_ID:
            guild = discord.Object(id=Config.SERVER_ID)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            logger.info("Synced %s command(s) to guild %s", len(synced), Config.SERVER_ID)
        else:
            synced = await bot.tree.sync()
            logger.info("Synced %s global command(s)", len(synced))
    except Exception as exc:
        logger.exception("Failed to sync commands: %s", exc)

    await set_bot_status()


@bot.event
async def on_error(event, *args, **kwargs):
    """Log unexpected Discord event errors."""
    logger.error("Error in %s: %s", event, (args, kwargs), exc_info=True)


async def set_bot_status():
    """Set bot status with member count when the configured guild is cached."""
    guild = bot.get_guild(Config.SERVER_ID) if Config.SERVER_ID else None
    if guild:
        activity_name = f"{guild.member_count} members | /help"
    else:
        activity_name = f"{Config.BRAND_NAME} | /help"

    activity = discord.Activity(type=discord.ActivityType.watching, name=activity_name)
    await bot.change_presence(activity=activity)


async def load_cogs():
    """Load all cogs from the cogs folder."""
    cogs_path = Path(__file__).resolve().parent / "cogs"
    for filename in os.listdir(cogs_path):
        if not filename.endswith(".py") or filename.startswith("_"):
            continue

        extension = f"cogs.{filename[:-3]}"
        try:
            await bot.load_extension(extension)
            logger.info("Loaded cog: %s", extension)
        except Exception as exc:
            logger.exception("Failed to load cog %s: %s", extension, exc)


async def setup_hook():
    """Initialize persistent storage and load extensions."""
    await db.initialize()
    await load_cogs()


bot.setup_hook = setup_hook


async def main():
    """Start the Render keep-alive webserver and the Discord bot."""
    try:
        if not Config.DISCORD_TOKEN:
            raise ValueError("DISCORD_TOKEN is not set in environment variables.")

        webserver.keep_alive()

        async with bot:
            await bot.start(Config.DISCORD_TOKEN)

    except KeyboardInterrupt:
        logger.info("Bot shutting down...")
    except Exception as exc:
        logger.exception("Fatal error: %s", exc)


if __name__ == "__main__":
    asyncio.run(main())
