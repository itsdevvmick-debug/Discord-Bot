import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*args, **kwargs):
        return False


load_dotenv()


def _int_env(name: str, default: int = 0) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default

    try:
        return int(value.strip())
    except ValueError:
        # Keep startup alive when .env.example placeholders are still present.
        return default


def _sqlite_url_to_path(value: str | None, default: str = "bot_database.db") -> str:
    if not value:
        return default
    if value.startswith("sqlite:///"):
        return value.removeprefix("sqlite:///")
    if value.startswith("sqlite://"):
        return value.removeprefix("sqlite://")
    return value


class Config:
    """Bot configuration loaded from environment variables."""

    BRAND_NAME = os.getenv("BRAND_NAME", "Avenue Assets")
    BRAND_SHORT_NAME = os.getenv("BRAND_SHORT_NAME", "Avenue")
    BUSINESS_DESCRIPTION = os.getenv(
        "BUSINESS_DESCRIPTION",
        "a Roblox asset and development shop",
    )

    DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

    MODERATOR_ROLE_ID = _int_env("MODERATOR_ROLE_ID")
    MARKETING_ROLE_ID = _int_env("MARKETING_ROLE_ID")
    CEO_ROLE_ID = _int_env("CEO_ROLE_ID")
    COO_ROLE_ID = _int_env("COO_ROLE_ID")
    TEAM_LEADER_ROLE_ID = _int_env("TEAM_LEADER_ROLE_ID")
    SUPPORT_ROLE_ID = _int_env("SUPPORT_ROLE_ID")
    MANAGEMENT_ROLE_ID = _int_env("MANAGEMENT_ROLE_ID")

    SUPPORT_TICKET_CHANNEL_ID = _int_env("SUPPORT_TICKET_CHANNEL_ID")
    MARKETING_TICKET_CHANNEL_ID = _int_env("MARKETING_TICKET_CHANNEL_ID")
    MANAGEMENT_TICKET_CHANNEL_ID = _int_env("MANAGEMENT_TICKET_CHANNEL_ID")
    PARTNERS_CHANNEL_ID = _int_env("PARTNERS_CHANNEL_ID")
    PARTNER_LOGS_CHANNEL_ID = _int_env("PARTNER_LOGS_CHANNEL_ID")
    MARKETING_ANNOUNCEMENTS_CHANNEL_ID = _int_env("MARKETING_ANNOUNCEMENTS_CHANNEL_ID")
    MARKETING_LOGS_CHANNEL_ID = _int_env("MARKETING_LOGS_CHANNEL_ID")
    MAIN_ANNOUNCEMENTS_CHANNEL_ID = _int_env("MAIN_ANNOUNCEMENTS_CHANNEL_ID")
    LOGS_CHANNEL_ID = _int_env("LOGS_CHANNEL_ID")
    TICKET_LOGS_CHANNEL_ID = _int_env("TICKET_LOGS_CHANNEL_ID")
    WELCOME_CHANNEL_ID = _int_env("WELCOME_CHANNEL_ID")
    GOODBYE_CHANNEL_ID = _int_env("GOODBYE_CHANNEL_ID")

    SUPPORT_CATEGORY_ID = _int_env("SUPPORT_CATEGORY_ID")
    MARKETING_CATEGORY_ID = _int_env("MARKETING_CATEGORY_ID")
    MANAGEMENT_CATEGORY_ID = _int_env("MANAGEMENT_CATEGORY_ID")

    PRODUCTS_FORUM_CHANNEL_ID = _int_env("PRODUCTS_FORUM_CHANNEL_ID")

    SERVER_ID = _int_env("SERVER_ID")
    BOT_PREFIX = os.getenv("BOT_PREFIX", "!")

    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///bot_database.db")
    DATABASE_PATH = os.getenv("DATABASE_PATH") or _sqlite_url_to_path(DATABASE_URL)

    RENDER_PORT = _int_env("PORT", 10000)
    GIVEAWAY_EMOJI = os.getenv("GIVEAWAY_EMOJI", "\N{PARTY POPPER}")

    BASE_DIR = Path(__file__).resolve().parent
