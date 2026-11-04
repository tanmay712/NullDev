import os
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("TOKEN", "")

DEFAULT_PREFIX = os.getenv("PREFIX", "Cz!")

OWNERS = {int(x) for x in os.getenv("OWNERS", "").split(",") if x.strip().isdigit()}

# ------------------------------------------------------------------ branding
# The NullDev community the bot is built for. Used by `Cz!discord`, the help
# menu, tickets, /about and the footer of most panels.
BRAND_NAME = os.getenv("BRAND_NAME", "NullDev")
SUPPORT_SERVER_URL = os.getenv("SUPPORT_SERVER_URL", "https://dc.definescloud.site")

TRACKER_SEED_GUILD_ID = int(os.getenv("TRACKER_SEED_GUILD_ID", "0") or 0)
TRACKER_SEED_CHANNEL_ID = int(os.getenv("TRACKER_SEED_CHANNEL_ID", "0") or 0)
TRACKER_SEED_BOT_IDS = [int(x) for x in os.getenv("TRACKER_SEED_BOT_IDS", "").split(",") if x.strip().isdigit()]

# Optional: set to a server ID to sync slash commands to that one guild instantly
# (for testing). Leave unset/0 to sync globally, which can take up to an hour
# to show up everywhere.
SLASH_SYNC_GUILD_ID = int(os.getenv("SLASH_SYNC_GUILD_ID", "0") or 0)
