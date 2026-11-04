from __future__ import annotations

import time

import discord
from discord import ui
from discord.ext import commands

from codezmanager import ui as nui
from codezmanager.emojis import E
from codezmanager.emojis import E as _EMGR
import config as cfgmod

_LOCAL_KEY_MAP = {"success": "SUCCESS", "error": "ERROR"}

def ES(key: str) -> str:
    return _EMGR[_LOCAL_KEY_MAP.get(key, key.upper())]

def _status_view(ok: bool, text: str) -> ui.LayoutView:
    return nui.simple_view(text, ok=ok)

# Every category is tagged with its NullDev emoji.
CATEGORY_META = {
    "NullDev": f"{E.NULLDEV} NullDev Community",
    "Greet": f"{E.FLOWERS} Greet / Welcome",
    "Suggestions": f"{E.STAR} Suggestions",
    "Moderation": f"{E.WARNING} Moderation",
    "Tickets": f"{E.GIFT} Tickets",
    "TeamSetup": f"{E.ONLINE} Team Setup",
    "BotAccess": f"{E.PERSON} Bot Access",
    "Feedback": f"{E.INFO} Feedback",
    "BotStatusTracker": f"{E.LOADING} Status Tracker",
    "VoiceStay": f"{E.GAMES} Voice Stay",
    "Tag": f"{E.UTILITY} Display Name Style",
    "Help": f"{E.HOME} General",
}

HELP_OVERRIDES = {
    "discord": "Get the NullDev Discord invite.",
    "invite": "Get the bot's invite link for your own server.",
    "greet": "Open the greet control panel.",
    "greet add": "Add a greet channel (max 3).",
    "greet remove": "Remove a greet channel.",
    "greet mode": "Set a channel's mode: simple or container.",
    "greet toggle": "Enable/disable a greet channel without removing it.",
    "greet autodelete": "Set auto-delete seconds for a channel's greet messages (0 = off).",
    "greet test": "Send a test greet message to a channel.",
    "greet list": "List configured greet channels.",
    "greet variables": "Show the template variables you can use.",
    "suggest": "Submit a suggestion (or post directly in the suggestion channel).",
    "suggest setchannel": "Set the channel where suggestions get posted as cards.",
    "suggest removechannel": "Remove the suggestion channel.",
    "suggest logchannel": "Set a log channel for suggestions (optional).",
    "suggest threshold": "Set the upvote threshold for the log channel (optional).",
    "suggest moderate": "Mark a suggestion approved/denied/considered by message ID.",
    "kick": "Kick a member from the server.",
    "ban": "Ban a member from the server.",
    "unban": "Unban a user by their ID.",
    "mute": "Timeout (mute) a member for a duration (e.g. 10m, 1h, 2d).",
    "unmute": "Remove a member's mute/timeout.",
    "warn": "Warn a member (logged with a case number).",
    "warnings": "Show a member's warning history.",
    "clearwarnings": "Clear all warnings for a member.",
    "purge": "Bulk-delete messages, optionally filtered by member.",
    "say": "Make the bot say something in this channel. Admins only.",
    "user": "Manage per-user daily action limits.",
    "user limit": "Manage per-user daily action limits.",
    "user limit set": "Set a daily ban/kick/mute limit for a staff member. Owner only.",
    "user limit clear": "Remove a daily action limit for a staff member. Owner only.",
    "user limit show": "Show a member's daily action limits and today's usage.",
    "ticket": "Show ticket system setup commands.",
    "ticket panel": "Post the ticket panel in this channel.",
    "ticket category": "Set the category where new ticket channels are created.",
    "ticket role": "Set the support role that can view and manage tickets.",
    "ticket logs": "Set the channel where closed ticket transcripts are posted.",
    "ticket close": "Close the current ticket channel.",
    "botaccess": "Manage who can use action commands. Owner only.",
    "botaccess add": "Give a user access to action commands. Owner only.",
    "botaccess remove": "Remove a user's access to action commands. Owner only.",
    "botaccess list": "List everyone with bot access. Owner only.",
    "teamsetup": "Track existing roles as staff roles: teamsetup @role @role. Owner only.",
    "teamroles": "List the currently tracked staff roles. Owner only.",
    "teamremoverole": "Stop tracking a staff role. Owner only.",
    "teampanel": "Post the daily staff availability panel in a channel. Owner only.",
    "teamrefresh": "Force-update the staff panel now. Owner only.",
    "feedback": "Post the feedback panel here.",
    "feedback setchannel": "Set the channel where feedback cards get posted.",
    "feedback removechannel": "Remove the feedback channel.",
    "feedback panel": "Post the feedback panel in a specific channel.",
    "tracker": "Show the live bot-status panel.",
    "tracker add": "Start tracking a bot's online/offline status.",
    "tracker remove": "Stop tracking a bot.",
    "tracker panel": "Post the live-updating status panel in a channel.",
    "tracker alertchannel": "Set the channel for status-change alerts.",
    "tracker list": "Show tracked bots and their current status.",
    "tracker refresh": "Manually refresh the status panel.",
    "join": "Join a voice channel and stay connected until kicked or `leave`.",
    "leave": "Disconnect from voice.",
    "tag": "Customize this bot's display name style (fonts/effects/colors).",
    "help": "Show this help menu.",
    "ping": "Check whether the bot is alive and its latency.",
}

def _iter_commands(cog: commands.Cog):
    for cmd in cog.get_commands():
        if cmd.hidden:
            continue
        if isinstance(cmd, commands.Group):
            if cmd.invoke_without_command:
                yield (f"{cmd.qualified_name} {cmd.signature}".strip(), HELP_OVERRIDES.get(cmd.qualified_name, cmd.help or "Opens the panel."))
            for sub in cmd.commands:
                if sub.hidden:
                    continue
                yield (f"{sub.qualified_name} {sub.signature}".strip(), HELP_OVERRIDES.get(sub.qualified_name, sub.help or "—"))
        else:
            yield (f"{cmd.qualified_name} {cmd.signature}".strip(), HELP_OVERRIDES.get(cmd.qualified_name, cmd.help or "—"))

def _build_overview(bot: commands.Bot) -> ui.Container:
    c = ui.Container(accent_colour=nui.BLURPLE)
    c.add_item(ui.TextDisplay(f"# {E.HOME} CodeZ Manager — Help"))
    c.add_item(ui.Separator())

    prefix = cfgmod.DEFAULT_PREFIX
    lines = [
        f"{E.LOADING} **Prefix:** `{prefix}` — e.g. `{prefix}help`, `{prefix}ping`",
        f"{E.PERSON} **Slash commands** work too: `/about`, `/emoji`, `/discord`",
        "",
    ]
    for cog_name, title in CATEGORY_META.items():
        cog = bot.get_cog(cog_name)
        count = len(list(_iter_commands(cog))) if cog else 0
        if count:
            lines.append(f"**{title}** — {count} command(s)")
    c.add_item(ui.TextDisplay("\n".join(lines)))
    c.add_item(ui.Separator(visible=False))
    c.add_item(ui.TextDisplay(nui.lead("NULLDEV", f"Need help? Join **{cfgmod.BRAND_NAME}** → {cfgmod.SUPPORT_SERVER_URL}")))
    c.add_item(ui.TextDisplay(f"-# {E.INFO} Pick a category below to see commands and usage."))
    return c

def _build_category(bot: commands.Bot, cog_name: str) -> ui.Container:
    title = CATEGORY_META.get(cog_name, cog_name)
    cog = bot.get_cog(cog_name)
    c = ui.Container(accent_colour=nui.BLURPLE)
    c.add_item(ui.TextDisplay(f"# {title}"))
    c.add_item(ui.Separator())

    if not cog:
        c.add_item(ui.TextDisplay(nui.lead("WARNING", "This category isn't loaded.")))
        return c

    prefix = cfgmod.DEFAULT_PREFIX
    entries = list(_iter_commands(cog))
    if not entries:
        c.add_item(ui.TextDisplay(nui.lead("INFO", "No commands here.")))
    else:
        lines = [f"{E.TICK} `{prefix}{usage}`\n-# {help_text}" for usage, help_text in entries]
        c.add_item(ui.TextDisplay("\n".join(lines)))
    c.add_item(ui.Separator(visible=False))
    c.add_item(ui.TextDisplay(nui.footer_line(f"{cfgmod.BRAND_NAME} community")))
    c.add_item(ui.ActionRow(nui.support_button()))
    return c

class HelpSelectView(ui.LayoutView):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=180)
        self.bot = bot
        self._container = _build_overview(bot)

        options = [discord.SelectOption(label="Overview", value="__overview__", default=True)]
        for cog_name, title in CATEGORY_META.items():
            cog = bot.get_cog(cog_name)
            if cog and list(_iter_commands(cog)):
                options.append(discord.SelectOption(label=title, value=cog_name))

        select = ui.Select(placeholder="Choose a category...", options=options)
        select.callback = self.on_select

        self._container.add_item(ui.ActionRow(select))
        self._container.add_item(ui.ActionRow(nui.support_button()))
        self.add_item(self._container)
        self._select = select

    async def on_select(self, interaction: discord.Interaction):
        value = interaction.data["values"][0]
        new_view = HelpSelectView(self.bot)
        for opt in new_view._select.options:
            opt.default = (opt.value == value)
        if value == "__overview__":
            body = _build_overview(self.bot)
        else:
            body = _build_category(self.bot, value)
        new_view.remove_item(new_view._container)
        body.add_item(ui.ActionRow(new_view._select))
        new_view._container = body
        new_view.add_item(body)
        await interaction.response.edit_message(view=new_view)

class Help(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._start_time = time.monotonic()

    @commands.command(name="help", help="Shows this help menu.")
    async def help_cmd(self, ctx: commands.Context):
        await ctx.send(view=HelpSelectView(self.bot))

    @commands.command(name="ping", help="Checks whether the bot is alive and its latency.")
    async def ping(self, ctx: commands.Context):
        latency_ms = round(self.bot.latency * 1000)
        uptime_s = int(time.monotonic() - self._start_time)
        h, rem = divmod(uptime_s, 3600)
        m, s = divmod(rem, 60)
        detail = (
            f"{E.ONLINE} **Pong!** `{latency_ms}ms`\n"
            f"{E.LOADING} **Uptime:** `{h}h {m}m {s}s`\n"
            f"{E.UTILITY} **Prefix:** `{cfgmod.DEFAULT_PREFIX}`\n"
            f"{E.GAMES} **Guilds:** `{len(self.bot.guilds)}`"
        )
        await ctx.send(view=nui.simple_view(detail, ok=True))

async def setup(bot: commands.Bot):
    await bot.add_cog(Help(bot))
