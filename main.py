import asyncio
import logging

import discord
from discord import ui
from discord.ext import commands

import config

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")
log = logging.getLogger("codezmanager")

INTENTS = discord.Intents.default()
INTENTS.members = True
INTENTS.message_content = True
INTENTS.presences = True


def _case_insensitive_prefix(bot: commands.Bot, message: discord.Message):
    """Accepts the prefix in any case: cz!, Cz!, CZ!, etc."""
    configured = config.DEFAULT_PREFIX
    prefixes = [configured]

    content = message.content
    if content[: len(configured)].lower() == configured.lower():
        # Return the exact-cased prefix actually used so command parsing lines up.
        prefixes = [content[: len(configured)], configured]

    return commands.when_mentioned_or(*prefixes)(bot, message)


class CodeZManager(commands.Bot):
    def __init__(self):
        super().__init__(
            command_prefix=_case_insensitive_prefix,
            intents=INTENTS,
            help_command=None,
            owner_ids=config.OWNERS or None,
        )

    async def setup_hook(self):
        from codezmanager import access, emoji_store
        from cogs import greet, suggestions, moderation, feedback, bot_status, voice_stay, tickets, teamsetup

        await greet.init_db()
        await suggestions.init_db()
        await moderation.init_db()
        await feedback.init_db()
        await bot_status.init_db()
        await voice_stay.init_db()
        await tickets.init_db()
        await teamsetup.init_db()
        await access.init_db()
        await emoji_store.init_db()

        for ext in (
            "cogs.greet",
            "cogs.suggestions",
            "cogs.moderation",
            "cogs.feedback",
            "cogs.bot_status",
            "cogs.voice_stay",
            "cogs.tag",
            "cogs.tickets",
            "cogs.teamsetup",
            "cogs.botaccess",
            "cogs.help",
            "cogs.emojimanager",
            "cogs.about",
        ):
            await self.load_extension(ext)

        log.info("Cogs loaded: %s", ", ".join(self.cogs.keys()))
        log.info("Prefix is %r — commands look like: %shelp, %sping", config.DEFAULT_PREFIX, config.DEFAULT_PREFIX, config.DEFAULT_PREFIX)

        if config.SLASH_SYNC_GUILD_ID:
            guild = discord.Object(id=config.SLASH_SYNC_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            log.info("Synced %d slash command(s) to guild %s (instant).", len(synced), config.SLASH_SYNC_GUILD_ID)
        else:
            synced = await self.tree.sync()
            log.info("Synced %d slash command(s) globally (can take up to 1 hour to appear).", len(synced))

    async def on_ready(self):
        log.info("Logged in as %s (%s)", self.user, self.user.id)
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name=f"{config.DEFAULT_PREFIX}help")
        )

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound):
            return

        if isinstance(error, commands.NotOwner):
            text = "Only the bot owner can use this command."
        elif isinstance(error, commands.MissingPermissions):
            text = f"You need: `{', '.join(error.missing_permissions)}`"
        elif isinstance(error, commands.BotMissingPermissions):
            text = f"I need: `{', '.join(error.missing_permissions)}`"
        elif isinstance(error, commands.MissingRequiredArgument):
            text = f"Missing argument: `{error.param.name}`. Try `{config.DEFAULT_PREFIX}help`."
        elif isinstance(error, commands.BadArgument):
            text = f"Bad argument: {error}"
        elif isinstance(error, commands.NoPrivateMessage):
            text = "That only works inside a server."
        elif isinstance(error, commands.CommandOnCooldown):
            text = f"Slow down — try again in {error.retry_after:.1f}s."
        else:
            log.exception("Unhandled command error in %s: %r", ctx.command, error, exc_info=error)
            text = f"Something went wrong running that command: `{error}`"

        view = ui.LayoutView()
        c = ui.Container()
        c.add_item(ui.TextDisplay(text))
        view.add_item(c)
        await ctx.send(view=view)

async def main():
    if not config.TOKEN:
        raise SystemExit("TOKEN is missing — set it in your .env file.")

    bot = CodeZManager()
    async with bot:
        await bot.start(config.TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
