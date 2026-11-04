from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
import discord
from discord import ui
from discord.ext import commands

from codezmanager.emojis import E
from codezmanager.emojis import E as _EMGR
from codezmanager import access
from codezmanager import ui as nui
import config as cfgmod

DB_DIR = Path("db")
DB_PATH = DB_DIR / "moderation.db"

_LOCAL_KEY_MAP = {"success": "SUCCESS", "error": "ERROR"}


def ES(key: str) -> str:
    return _EMGR[_LOCAL_KEY_MAP.get(key, key.upper())]


def _status_view(ok: bool, text: str) -> ui.LayoutView:
    """Green + NullDev tick on success, red + NullDev cross on failure."""
    return nui.simple_view(text, ok=ok)


def _info_view(text: str) -> ui.LayoutView:
    """Neutral blue container for usage / informational messages."""
    return nui.simple_view(text, accent=nui.BLURPLE)


ACTIONS = ("ban", "kick", "mute")

_DURATION_RE = re.compile(r"^(\d+)([smhdw])$", re.IGNORECASE)
_UNIT_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400, "w": 604800}


def _parse_duration(text: str | None) -> int | None:
    if not text:
        return None
    m = _DURATION_RE.match(text.strip())
    if not m:
        return None
    amount, unit = m.groups()
    return int(amount) * _UNIT_SECONDS[unit.lower()]


def _ensure_db():
    DB_DIR.mkdir(exist_ok=True)


async def init_db():
    _ensure_db()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS user_limits (
                guild_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                action   TEXT NOT NULL,
                daily_limit INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id, action)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS action_log (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                action     TEXT NOT NULL,
                target_id  INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS warnings (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason     TEXT,
                created_at INTEGER NOT NULL
            )
            """
        )
        await db.commit()


async def set_user_limit(guild_id: int, user_id: int, action: str, daily_limit: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO user_limits (guild_id, user_id, action, daily_limit) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, action) DO UPDATE SET daily_limit = excluded.daily_limit",
            (guild_id, user_id, action, daily_limit),
        )
        await db.commit()


async def clear_user_limit(guild_id: int, user_id: int, action: str):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "DELETE FROM user_limits WHERE guild_id = ? AND user_id = ? AND action = ?",
            (guild_id, user_id, action),
        )
        await db.commit()


async def get_user_limit(guild_id: int, user_id: int, action: str) -> int | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "SELECT daily_limit FROM user_limits WHERE guild_id = ? AND user_id = ? AND action = ?",
            (guild_id, user_id, action),
        )
        row = await cur.fetchone()
        return row[0] if row else None


async def get_all_limits(guild_id: int, user_id: int) -> dict:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "SELECT action, daily_limit FROM user_limits WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return {row[0]: row[1] for row in await cur.fetchall()}


async def count_actions_today(guild_id: int, user_id: int, action: str) -> int:
    since = int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "SELECT COUNT(*) FROM action_log WHERE guild_id = ? AND user_id = ? AND action = ? AND created_at >= ?",
            (guild_id, user_id, action, since),
        )
        row = await cur.fetchone()
        return row[0] if row else 0


async def log_action(guild_id: int, user_id: int, action: str, target_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO action_log (guild_id, user_id, action, target_id, created_at) VALUES (?, ?, ?, ?, strftime('%s','now'))",
            (guild_id, user_id, action, target_id),
        )
        await db.commit()


async def add_warning(guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) VALUES (?, ?, ?, ?, strftime('%s','now'))",
            (guild_id, user_id, moderator_id, reason),
        )
        await db.commit()
        return cur.lastrowid


async def get_warnings(guild_id: int, user_id: int) -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
            (guild_id, user_id),
        )
        return [dict(r) for r in await cur.fetchall()]


async def clear_warnings(guild_id: int, user_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (guild_id, user_id))
        await db.commit()


async def _check_and_consume_limit(ctx: commands.Context, action: str) -> tuple[bool, str | None]:
    """Returns (allowed, error_text). Bot owners and server owner bypass limits."""
    if await ctx.bot.is_owner(ctx.author) or ctx.author.id == ctx.guild.owner_id:
        return True, None

    limit = await get_user_limit(ctx.guild.id, ctx.author.id, action)
    if limit is None:
        return True, None

    used = await count_actions_today(ctx.guild.id, ctx.author.id, action)
    if used >= limit:
        return False, f"You have reached your daily limit of `{limit}` for `{action}` (used `{used}` in the last 24h)."
    return True, None


class Moderation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------------- kick
    @commands.command(name="kick", help="Kick a member from the server.")
    @commands.guild_only()
    @access.action_command(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if member.id == ctx.author.id:
            await ctx.send(view=_status_view(False, "You cannot kick yourself."))
            return
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send(view=_status_view(False, "You cannot kick someone with an equal or higher role."))
            return

        allowed, err = await _check_and_consume_limit(ctx, "kick")
        if not allowed:
            await ctx.send(view=_status_view(False, err))
            return

        try:
            await member.kick(reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        except discord.Forbidden:
            await ctx.send(view=_status_view(False, "I do not have permission to kick that member."))
            return

        await log_action(ctx.guild.id, ctx.author.id, "kick", member.id)
        await ctx.send(view=_status_view(True, f"Kicked **{member.display_name}**. Reason: {reason}"))

    # ----------------------------------------------------------------- ban
    @commands.command(name="ban", help="Ban a member from the server.")
    @commands.guild_only()
    @access.action_command(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        if member.id == ctx.author.id:
            await ctx.send(view=_status_view(False, "You cannot ban yourself."))
            return
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send(view=_status_view(False, "You cannot ban someone with an equal or higher role."))
            return

        allowed, err = await _check_and_consume_limit(ctx, "ban")
        if not allowed:
            await ctx.send(view=_status_view(False, err))
            return

        try:
            await member.ban(reason=f"{ctx.author} ({ctx.author.id}): {reason}", delete_message_seconds=0)
        except discord.Forbidden:
            await ctx.send(view=_status_view(False, "I do not have permission to ban that member."))
            return

        await log_action(ctx.guild.id, ctx.author.id, "ban", member.id)
        await ctx.send(view=_status_view(True, f"Banned **{member.display_name}**. Reason: {reason}"))

    @commands.command(name="unban", help="Unban a user by their ID.")
    @commands.guild_only()
    @access.action_command(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, user_id: int, *, reason: str = "No reason provided"):
        try:
            user = discord.Object(id=user_id)
            await ctx.guild.unban(user, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        except discord.NotFound:
            await ctx.send(view=_status_view(False, "That user is not banned."))
            return
        except discord.Forbidden:
            await ctx.send(view=_status_view(False, "I do not have permission to unban that user."))
            return

        await ctx.send(view=_status_view(True, f"Unbanned user `{user_id}`. Reason: {reason}"))

    # ---------------------------------------------------------------- mute
    @commands.command(name="mute", help="Timeout (mute) a member for a duration (e.g. 10m, 1h, 2d). Alias for timeout.")
    @commands.guild_only()
    @access.action_command(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mute(self, ctx: commands.Context, member: discord.Member, duration: str = "1h", *, reason: str = "No reason provided"):
        if member.id == ctx.author.id:
            await ctx.send(view=_status_view(False, "You cannot mute yourself."))
            return
        if member.top_role >= ctx.author.top_role and ctx.author.id != ctx.guild.owner_id:
            await ctx.send(view=_status_view(False, "You cannot mute someone with an equal or higher role."))
            return

        seconds = _parse_duration(duration)
        if seconds is None:
            await ctx.send(view=_status_view(False, "Invalid duration. Use a format like `10m`, `1h`, `2d`."))
            return
        if seconds > 28 * 86400:
            await ctx.send(view=_status_view(False, "Discord timeouts cannot exceed 28 days."))
            return

        allowed, err = await _check_and_consume_limit(ctx, "mute")
        if not allowed:
            await ctx.send(view=_status_view(False, err))
            return

        until = discord.utils.utcnow() + timedelta(seconds=seconds)
        try:
            await member.timeout(until, reason=f"{ctx.author} ({ctx.author.id}): {reason}")
        except discord.Forbidden:
            await ctx.send(view=_status_view(False, "I do not have permission to mute that member."))
            return

        await log_action(ctx.guild.id, ctx.author.id, "mute", member.id)
        await ctx.send(view=_status_view(True, f"Muted **{member.display_name}** for `{duration}`. Reason: {reason}"))

    @commands.command(name="unmute", help="Remove a member's mute/timeout.")
    @commands.guild_only()
    @access.action_command(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member):
        try:
            await member.timeout(None, reason=f"Unmuted by {ctx.author} ({ctx.author.id})")
        except discord.Forbidden:
            await ctx.send(view=_status_view(False, "I do not have permission to unmute that member."))
            return
        await ctx.send(view=_status_view(True, f"Unmuted **{member.display_name}**."))

    # ------------------------------------------------------------- purge
    @commands.command(name="purge", help="Bulk-delete messages, optionally filtered by member.")
    @commands.guild_only()
    @access.action_command(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int, member: discord.Member = None):
        if amount < 1 or amount > 200:
            await ctx.send(view=_status_view(False, "Amount must be between 1 and 200."))
            return

        def check(msg: discord.Message) -> bool:
            return member is None or msg.author.id == member.id

        await ctx.message.delete()
        deleted = await ctx.channel.purge(limit=amount, check=check)
        note = await ctx.send(view=_status_view(True, f"Deleted `{len(deleted)}` message(s)."))
        await note.delete(delay=5)

    # ------------------------------------------------------------- warn
    @commands.command(name="warn", help="Warn a member (logged with a case number).")
    @commands.guild_only()
    @access.action_command(moderate_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        case_id = await add_warning(ctx.guild.id, member.id, ctx.author.id, reason)
        await ctx.send(view=_status_view(True, f"Warned **{member.display_name}**. Case `#{case_id}`. Reason: {reason}"))

    @commands.command(name="warnings", help="Show a member's warning history.")
    @commands.guild_only()
    @access.action_command(moderate_members=True)
    async def warnings_cmd(self, ctx: commands.Context, member: discord.Member):
        rows = await get_warnings(ctx.guild.id, member.id)
        if not rows:
            await ctx.send(view=_status_view(False, f"**{member.display_name}** has no warnings."))
            return

        lines = [nui.lead("WARNING", f"**Warnings for {member.display_name}** — {len(rows)} total"), ""]
        for row in rows[:15]:
            mod = ctx.guild.get_member(row["moderator_id"])
            mod_name = mod.display_name if mod else f"ID {row['moderator_id']}"
            lines.append(
                f"{E.WARNING} `#{row['id']}` by **{mod_name}** — {row['reason']} — <t:{row['created_at']}:R>"
            )

        view = ui.LayoutView()
        view.add_item(ui.Container(ui.TextDisplay("\n".join(lines)), accent_colour=nui.YELLOW))
        await ctx.send(view=view)

    @commands.command(name="clearwarnings", help="Clear all warnings for a member.")
    @commands.guild_only()
    @access.action_command(manage_guild=True)
    async def clearwarnings(self, ctx: commands.Context, member: discord.Member):
        await clear_warnings(ctx.guild.id, member.id)
        await ctx.send(view=_status_view(True, f"Cleared all warnings for **{member.display_name}**."))

    # --------------------------------------------------------- user limit
    @commands.group(name="user", invoke_without_command=True)
    @commands.guild_only()
    async def user_group(self, ctx: commands.Context):
        await ctx.send(view=_info_view(
            nui.lead("INFO", f"Use `{cfgmod.DEFAULT_PREFIX}user limit set <ban|kick|mute> <@user> <count>`."),
        ))

    @user_group.group(name="limit", invoke_without_command=True)
    @commands.guild_only()
    async def limit_group(self, ctx: commands.Context):
        await ctx.send(
            view=_info_view(
                f"{E.TICK} `{cfgmod.DEFAULT_PREFIX}user limit set <ban|kick|mute> <@user> <count>`\n"
                f"{E.TICK} `{cfgmod.DEFAULT_PREFIX}user limit clear <ban|kick|mute> <@user>`\n"
                f"{E.TICK} `{cfgmod.DEFAULT_PREFIX}user limit show <@user>`\n\n"
                f"-# {cfgmod.BRAND_NAME} — {cfgmod.SUPPORT_SERVER_URL}"
            )
        )

    @limit_group.command(name="set", help="Set a daily action limit for a staff member. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def limit_set(self, ctx: commands.Context, action: str, member: discord.Member, count: int):
        action = action.lower()
        if action not in ACTIONS:
            await ctx.send(view=_status_view(False, f"Action must be one of: `{', '.join(ACTIONS)}`."))
            return
        if count < 0:
            await ctx.send(view=_status_view(False, "Count cannot be negative."))
            return

        await set_user_limit(ctx.guild.id, member.id, action, count)
        await ctx.send(
            view=_status_view(True, f"**{member.display_name}** can now use `{action}` up to `{count}` time(s) per day.")
        )

    @limit_group.command(name="clear", help="Remove a daily action limit for a staff member. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def limit_clear(self, ctx: commands.Context, action: str, member: discord.Member):
        action = action.lower()
        if action not in ACTIONS:
            await ctx.send(view=_status_view(False, f"Action must be one of: `{', '.join(ACTIONS)}`."))
            return
        await clear_user_limit(ctx.guild.id, member.id, action)
        await ctx.send(view=_status_view(True, f"Removed the `{action}` limit for **{member.display_name}**."))

    @limit_group.command(name="show", help="Show a member's daily action limits and today's usage.")
    @commands.guild_only()
    async def limit_show(self, ctx: commands.Context, member: discord.Member):
        limits = await get_all_limits(ctx.guild.id, member.id)
        if not limits:
            await ctx.send(view=_status_view(True, f"**{member.display_name}** has no configured limits."))
            return

        lines = [nui.lead("UTILITY", f"**Limits for {member.display_name}**"), ""]
        for action, limit in limits.items():
            used = await count_actions_today(ctx.guild.id, member.id, action)
            icon = E.TICK if used < limit else E.CROSS
            lines.append(f"{icon} `{action}`: `{used}/{limit}` used in the last 24h")

        view = ui.LayoutView()
        c = ui.Container()
        c.add_item(ui.TextDisplay("\n".join(lines)))
        view.add_item(c)
        await ctx.send(view=view)

    # ------------------------------------------------------------- say
    @commands.command(name="say", help="Make the bot say something in this channel. Admins only.")
    @commands.guild_only()
    @access.action_command(administrator=True)
    async def say(self, ctx: commands.Context, channel: discord.TextChannel = None, *, message: str):
        target = channel or ctx.channel
        try:
            await ctx.message.delete()
        except discord.HTTPException:
            pass

        # Bot owners keep full control. Everyone else (including people on the
        # bot-access list) can't use `say` to ping @everyone, @here, or roles.
        if await ctx.bot.is_owner(ctx.author):
            mentions = discord.AllowedMentions.all()
        else:
            mentions = discord.AllowedMentions(everyone=False, roles=False, users=True)

        try:
            await target.send(message, allowed_mentions=mentions)
        except discord.Forbidden:
            await ctx.send(view=_status_view(False, "I do not have permission to send messages in that channel."))
            return

        if target.id != ctx.channel.id:
            note = await ctx.send(view=_status_view(True, f"Sent to {target.mention}."))
            await note.delete(delay=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
