from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite
import discord
from discord import ui
from discord.ext import commands, tasks

import config as cfgmod
from codezmanager.emojis import E as _EMGR
from codezmanager import ui as nui
from codezmanager.emojis import E

DB_DIR = Path("db")
DB_PATH = DB_DIR / "teamsetup.db"

AVAILABLE_STATUSES = {discord.Status.online, discord.Status.idle, discord.Status.dnd}

WARNING_TEXT = "Don't ping unavailable support members."


def _e(key: str) -> str:
    """Custom emoji for a key (returns '' if not filled in emojis.json)."""
    return _EMGR[key]


def _with(emoji: str, text: str) -> str:
    return f"{emoji} {text}" if emoji else text


def _view(text: str, ok: bool | None = None) -> ui.LayoutView:
    """A single-container view; ``ok`` adds the NullDev tick/cross + accent."""
    return nui.simple_view(text, ok=ok)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ------------------------------------------------------------------ database
async def init_db():
    DB_DIR.mkdir(exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS team_config (
                guild_id           INTEGER PRIMARY KEY,
                panel_channel_id   INTEGER,
                panel_message_id   INTEGER,
                panel_date         TEXT
            )
            """
        )
        # Older versions had announce_channel_id / report_channel_id columns.
        # Add the new panel columns if this DB was created by an older version.
        cur = await db.execute("PRAGMA table_info(team_config)")
        existing = {row[1] for row in await cur.fetchall()}
        for col, decl in (
            ("panel_channel_id", "INTEGER"),
            ("panel_message_id", "INTEGER"),
            ("panel_date", "TEXT"),
        ):
            if col not in existing:
                await db.execute(f"ALTER TABLE team_config ADD COLUMN {col} {decl}")

        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS team_roles (
                guild_id INTEGER NOT NULL,
                role_id  INTEGER NOT NULL,
                label    TEXT NOT NULL,
                PRIMARY KEY (guild_id, role_id)
            )
            """
        )
        await db.commit()


async def get_config(guild_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM team_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_config(guild_id: int, **fields):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO team_config (guild_id) VALUES (?) ON CONFLICT(guild_id) DO NOTHING",
            (guild_id,),
        )
        if fields:
            cols = ", ".join(f"{k} = ?" for k in fields)
            await db.execute(
                f"UPDATE team_config SET {cols} WHERE guild_id = ?",
                list(fields.values()) + [guild_id],
            )
        await db.commit()


async def all_configs() -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM team_config WHERE panel_channel_id IS NOT NULL")
        return [dict(r) for r in await cur.fetchall()]


async def add_team_role(guild_id: int, role_id: int, label: str) -> bool:
    """Save a role ID. Returns True if newly added, False if it was already tracked."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "SELECT 1 FROM team_roles WHERE guild_id = ? AND role_id = ?", (guild_id, role_id)
        )
        existed = await cur.fetchone() is not None
        await db.execute(
            "INSERT INTO team_roles (guild_id, role_id, label) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, role_id) DO UPDATE SET label = excluded.label",
            (guild_id, role_id, label),
        )
        await db.commit()
        return not existed


async def remove_team_role(guild_id: int, role_id: int) -> bool:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "DELETE FROM team_roles WHERE guild_id = ? AND role_id = ?", (guild_id, role_id)
        )
        await db.commit()
        return cur.rowcount > 0


async def get_team_roles(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM team_roles WHERE guild_id = ?", (guild_id,))
        return [dict(r) for r in await cur.fetchall()]


# --------------------------------------------------------------------- panel
def _staff_members(guild: discord.Guild, role_ids: set[int]) -> list[discord.Member]:
    """Every non-bot member holding at least one tracked role."""
    return [
        m for m in guild.members
        if not m.bot and any(r.id in role_ids for r in m.roles)
    ]


def _sort_key(member: discord.Member):
    return member.display_name.lower()


def _ts(now: datetime) -> str:
    """Discord relative timestamp. Discord renders 'X minutes ago' and keeps it fresh."""
    return f"<t:{int(now.timestamp())}:R>"


async def build_panel_view(guild: discord.Guild) -> ui.LayoutView:
    rows = await get_team_roles(guild.id)
    role_ids = {r["role_id"] for r in rows}
    staff = _staff_members(guild, role_ids)

    available = sorted((m for m in staff if m.status in AVAILABLE_STATUSES), key=_sort_key)
    unavailable = sorted((m for m in staff if m.status not in AVAILABLE_STATUSES), key=_sort_key)

    view = ui.LayoutView(timeout=None)
    c = ui.Container()

    if not role_ids:
        c.add_item(ui.TextDisplay(nui.lead(
            "WARNING", f"No team roles set. Run `{cfgmod.DEFAULT_PREFIX}teamsetup @role` first."
        )))
        view.add_item(c)
        return view

    # ---- Available
    c.add_item(ui.TextDisplay(f"### {_e('TEAM_AVAILABLE')} Available Support"))
    if available:
        c.add_item(ui.TextDisplay("\n".join(
            f"{nui.status_emoji(m.status)} **{m.display_name}**" for m in available
        )))
    else:
        c.add_item(ui.TextDisplay(nui.lead("OFFLINE", "*Nobody is available right now.*")))

    c.add_item(ui.Separator())

    # ---- Unavailable
    c.add_item(ui.TextDisplay(f"### {_e('TEAM_UNAVAILABLE')} Unavailable Support"))
    if unavailable:
        c.add_item(ui.TextDisplay("\n".join(
            f"{E.OFFLINE} {m.display_name}" for m in unavailable
        )))
    else:
        c.add_item(ui.TextDisplay(nui.lead("ONLINE", "*Everyone is available.*")))

    c.add_item(ui.Separator())

    # ---- Warning + footer
    c.add_item(ui.TextDisplay(_with(_e("TEAM_WARNING"), f"**{WARNING_TEXT}**")))
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay(
        f"{E.LOADING} Updated {_ts(discord.utils.utcnow())}\n"
        f"-# {cfgmod.BRAND_NAME} — {cfgmod.SUPPORT_SERVER_URL}"
    ))

    view.add_item(c)
    return view


def _signature(guild: discord.Guild, role_ids: set[int]) -> tuple:
    """What the panel visibly depends on. If this hasn't changed, don't edit."""
    return tuple(sorted(
        (m.id, m.display_name, m.status in AVAILABLE_STATUSES)
        for m in _staff_members(guild, role_ids)
    ))


# ----------------------------------------------------------------------- cog
class TeamSetup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._last_sig: dict[int, tuple] = {}
        self._pending: dict[int, asyncio.Task] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self.panel_loop.start()

    def cog_unload(self):
        self.panel_loop.cancel()
        for t in self._pending.values():
            t.cancel()

    def _lock(self, guild_id: int) -> asyncio.Lock:
        return self._locks.setdefault(guild_id, asyncio.Lock())

    # ---------------------------------------------------------------- commands
    @commands.command(name="teamsetup", help="Track existing roles as staff roles. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def teamsetup_cmd(self, ctx: commands.Context, roles: commands.Greedy[discord.Role]):
        """Usage: teamsetup @role [@role ...]. Only saves IDs of existing roles."""
        prefix = cfgmod.DEFAULT_PREFIX

        if not roles:
            await ctx.send(view=_view(
                nui.lead(
                    "PERSON",
                    f"### {E.PERSON} Team Setup\n"
                    "Mention the existing roles you want to track:\n"
                    f"{E.TICK} `{prefix}teamsetup @Staff @Moderator @Admin`",
                )
            ))
            return

        lines = []
        for role in roles:
            if role.is_default():
                lines.append(nui.lead("WARNING", "Skipped **@everyone** (cannot be tracked)"))
                continue
            newly_added = await add_team_role(ctx.guild.id, role.id, role.name)
            lines.append(
                nui.lead("TICK", f"Now tracking {role.mention}") if newly_added
                else nui.lead("INFO", f"Already tracking {role.mention} (updated)")
            )

        lines.append("")
        lines.append(nui.lead("UTILITY", f"Next: `{prefix}teampanel #channel`"))
        await ctx.send(view=_view(f"### {E.PERSON} Team Setup\n" + "\n".join(lines)))
        await self.refresh(ctx.guild)

    @commands.command(name="teamroles", help="List the currently tracked staff roles. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def teamroles(self, ctx: commands.Context):
        rows = await get_team_roles(ctx.guild.id)
        if not rows:
            await ctx.send(view=_view(
                nui.lead("WARNING", f"No team roles set. Run `{cfgmod.DEFAULT_PREFIX}teamsetup @role` first."),
                ok=False,
            ))
            return

        lines = [f"### {E.PERSON} Tracked Team Roles", ""]
        for row in rows:
            role = ctx.guild.get_role(row["role_id"])
            lines.append(f"{E.TICK} {role.mention} (`{role.id}`)" if role
                         else nui.lead("WARNING", f"Deleted role **{row['label']}** (`{row['role_id']}`)"))
        await ctx.send(view=_view("\n".join(lines)))

    @commands.command(name="teamremoverole", help="Stop tracking a staff role. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def teamremoverole(self, ctx: commands.Context, role: discord.Role):
        removed = await remove_team_role(ctx.guild.id, role.id)
        await ctx.send(view=_view(
            nui.lead("SUCCESS", f"Stopped tracking {role.mention}.") if removed
            else nui.lead("ERROR", f"{role.mention} was not being tracked."),
            ok=None,
        ))
        if removed:
            await self.refresh(ctx.guild)

    @commands.command(name="teampanel", help="Post the daily staff availability panel in a channel. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def teampanel(self, ctx: commands.Context, channel: discord.TextChannel):
        rows = await get_team_roles(ctx.guild.id)
        if not rows:
            await ctx.send(view=_view(
                nui.lead("WARNING", f"Set roles first: `{cfgmod.DEFAULT_PREFIX}teamsetup @role`"),
                ok=False,
            ))
            return

        # Point at the new channel and force a fresh post there.
        await set_config(ctx.guild.id, panel_channel_id=channel.id, panel_message_id=None, panel_date=None)
        ok = await self.refresh(ctx.guild, force=True)
        if ok:
            await ctx.send(view=_view(
                nui.lead(
                    "SUCCESS",
                    f"Panel posted in {channel.mention}. It will be edited through the day and a new one posted tomorrow.",
                ),
                ok=None,
            ))
        else:
            await ctx.send(view=_view(
                nui.lead(
                    "ERROR",
                    f"Could not post in {channel.mention}. Check that I can view and send messages there.",
                ),
                ok=False,
            ))

    @commands.command(name="teamrefresh", help="Force-update the staff panel now. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def teamrefresh(self, ctx: commands.Context):
        ok = await self.refresh(ctx.guild, force=True)
        await ctx.send(view=_view(
            nui.lead("SUCCESS", "Panel refreshed.") if ok
            else nui.lead("ERROR", f"No panel set. Run `{cfgmod.DEFAULT_PREFIX}teampanel #channel` first."),
            ok=None,
        ))

    # --------------------------------------------------------------- refreshing
    async def refresh(self, guild: discord.Guild, force: bool = False) -> bool:
        """Edit today's panel, or post a new one if the day changed / it's missing.

        Returns True if a panel exists afterwards.
        """
        async with self._lock(guild.id):
            cfg = await get_config(guild.id)
            if not cfg or not cfg.get("panel_channel_id"):
                return False

            channel = guild.get_channel(cfg["panel_channel_id"])
            if not isinstance(channel, discord.TextChannel):
                return False

            rows = await get_team_roles(guild.id)
            role_ids = {r["role_id"] for r in rows}
            sig = _signature(guild, role_ids)
            today = _today()
            is_new_day = cfg.get("panel_date") != today
            message_id = cfg.get("panel_message_id")

            # Nothing visible changed and it's still today's message -> skip the API call.
            if (not force and not is_new_day and message_id
                    and self._last_sig.get(guild.id) == sig):
                return True

            view = await build_panel_view(guild)

            # Same day and we have a message: edit it.
            if message_id and not is_new_day:
                try:
                    msg = await channel.fetch_message(message_id)
                    await msg.edit(view=view)
                    self._last_sig[guild.id] = sig
                    return True
                except discord.NotFound:
                    pass  # message was deleted, fall through and post a new one
                except discord.HTTPException:
                    return True  # transient error, keep the ID and try again next tick

            # New day, or no/deleted message: post a fresh one.
            try:
                msg = await channel.send(view=view)
            except discord.HTTPException:
                return False

            await set_config(guild.id, panel_message_id=msg.id, panel_date=today)
            self._last_sig[guild.id] = sig
            return True

    def _schedule(self, guild: discord.Guild):
        """Debounce: many presence updates in a burst become a single edit."""
        existing = self._pending.get(guild.id)
        if existing and not existing.done():
            return

        async def runner():
            try:
                await asyncio.sleep(3)
                await self.refresh(guild)
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            finally:
                self._pending.pop(guild.id, None)

        self._pending[guild.id] = asyncio.create_task(runner())

    # ---------------------------------------------------------------- listeners
    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if after.bot:
            return
        was = before.status in AVAILABLE_STATUSES
        now = after.status in AVAILABLE_STATUSES
        if was == now:
            return  # e.g. online -> idle, both "available": panel looks identical

        rows = await get_team_roles(after.guild.id)
        role_ids = {r["role_id"] for r in rows}
        if not any(r.id in role_ids for r in after.roles):
            return
        self._schedule(after.guild)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        # Role gained/lost or display name changed.
        if before.roles == after.roles and before.display_name == after.display_name:
            return
        self._schedule(after.guild)

    # --------------------------------------------------------------------- loop
    @tasks.loop(minutes=5)
    async def panel_loop(self):
        """Keeps the 'Updated ...' footer honest and handles the day rollover.

        Forced on purpose: without it, a quiet stretch (nobody changing status)
        would skip the edit and the footer would age to '6 hours ago' even though
        the panel is fully up to date.
        """
        for cfg in await all_configs():
            guild = self.bot.get_guild(cfg["guild_id"])
            if guild:
                try:
                    await self.refresh(guild, force=True)
                except Exception:
                    pass

    @panel_loop.before_loop
    async def before_panel_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(TeamSetup(bot))
