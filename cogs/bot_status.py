from __future__ import annotations

from pathlib import Path

import aiosqlite
import discord
from discord import ui
from discord.ext import commands, tasks

from codezmanager.emojis import E as _EMGR
from codezmanager import access
import config as cfgmod

DB_DIR = Path("db")
DB_PATH = DB_DIR / "bot_status.db"

_LOCAL_KEY_MAP = {"success": "SUCCESS", "error": "ERROR"}

STATUS_LABEL = {
    discord.Status.online: "Online",
    discord.Status.idle: "Idle",
    discord.Status.dnd: "Do Not Disturb",
    discord.Status.offline: "Offline",
    discord.Status.invisible: "Offline",
}

def ES(key: str) -> str:
    return _EMGR[_LOCAL_KEY_MAP.get(key, key.upper())]

def _status_view(ok: bool, text: str) -> ui.LayoutView:
    view = ui.LayoutView()
    c = ui.Container()
    c.add_item(ui.TextDisplay(text))
    view.add_item(c)
    return view

def _ensure_db():
    DB_DIR.mkdir(exist_ok=True)

async def init_db():
    _ensure_db()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS tracked_bots (
                guild_id INTEGER NOT NULL,
                bot_id   INTEGER NOT NULL,
                PRIMARY KEY (guild_id, bot_id)
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS tracker_config (
                guild_id        INTEGER PRIMARY KEY,
                panel_channel_id  INTEGER,
                panel_message_id  INTEGER,
                alert_channel_id  INTEGER
            )
            """
        )
        await db.commit()

async def add_tracked(guild_id: int, bot_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT OR IGNORE INTO tracked_bots (guild_id, bot_id) VALUES (?, ?)", (guild_id, bot_id)
        )
        await db.commit()

async def remove_tracked(guild_id: int, bot_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("DELETE FROM tracked_bots WHERE guild_id = ? AND bot_id = ?", (guild_id, bot_id))
        await db.commit()

async def get_tracked(guild_id: int) -> list[int]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute("SELECT bot_id FROM tracked_bots WHERE guild_id = ?", (guild_id,))
        return [r[0] for r in await cur.fetchall()]

async def get_config(guild_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM tracker_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def set_config(guild_id: int, **fields):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO tracker_config (guild_id) VALUES (?) ON CONFLICT(guild_id) DO NOTHING", (guild_id,)
        )
        if fields:
            cols = ", ".join(f"{k} = ?" for k in fields)
            await db.execute(
                f"UPDATE tracker_config SET {cols} WHERE guild_id = ?", list(fields.values()) + [guild_id]
            )
        await db.commit()

async def build_panel_view(bot: commands.Bot, guild: discord.Guild) -> ui.LayoutView:
    tracked_ids = await get_tracked(guild.id)
    now = discord.utils.utcnow()

    view = ui.LayoutView(timeout=None)
    c = ui.Container()
    c.add_item(ui.TextDisplay("### ZD Status\nReal-time bot status monitor"))
    c.add_item(ui.Separator())

    if not tracked_ids:
        c.add_item(ui.TextDisplay(f"No bots tracked yet. Use `{cfgmod.DEFAULT_PREFIX}tracker add @bot`."))
    else:
        c.add_item(ui.TextDisplay("__**Bot Status**__"))
        for bot_id in tracked_ids:
            member = guild.get_member(bot_id)
            if not member:
                text = ui.TextDisplay(f"## Unknown Bot\n**ID:** `{bot_id}`\n**Status:** Not in server")
                c.add_item(text)
                continue
            label = STATUS_LABEL.get(member.status, "Offline")
            status_prefix = ""
            text = ui.TextDisplay(
                f"## {member.display_name}\n"
                f"**Username:** @{member.name}\n"
                f"**ID:** `{member.id}`\n"
                f"**Status:** {status_prefix}{label}"
            )
            try:
                section = ui.Section(
                    text, accessory=ui.Thumbnail(media=discord.UnfurledMediaItem(url=str(member.display_avatar.url)))
                )
                c.add_item(section)
            except Exception:
                c.add_item(text)

    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay(f"**Last Updated:** <t:{int(now.timestamp())}:T>\n**Tracked:** {len(tracked_ids)} bot(s)"))
    view.add_item(c)
    return view

def _panel_signature(guild: discord.Guild, tracked_ids: list[int]) -> tuple:
    sig = []
    for bot_id in tracked_ids:
        member = guild.get_member(bot_id)
        sig.append((bot_id, member.status if member else None))
    return tuple(sig)

async def refresh_panel(bot: commands.Bot, guild: discord.Guild, force: bool = False, _cache: dict = {}):
    cfg = await get_config(guild.id)
    if not cfg or not cfg.get("panel_channel_id") or not cfg.get("panel_message_id"):
        return
    tracked_ids = await get_tracked(guild.id)
    sig = _panel_signature(guild, tracked_ids)
    if not force and _cache.get(guild.id) == sig:
        return
    channel = guild.get_channel(cfg["panel_channel_id"])
    if not channel:
        return
    try:
        msg = await channel.fetch_message(cfg["panel_message_id"])
        await msg.edit(view=await build_panel_view(bot, guild))
        _cache[guild.id] = sig
    except discord.HTTPException:
        pass

class BotStatusTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._seeded = False
        self.auto_refresh.start()

    def cog_unload(self):
        self.auto_refresh.cancel()

    async def cog_load(self):
        await self._seed_from_env()

    async def _seed_from_env(self):
        if self._seeded:
            return
        self._seeded = True

        guild_id = getattr(cfgmod, "TRACKER_SEED_GUILD_ID", 0)
        channel_id = getattr(cfgmod, "TRACKER_SEED_CHANNEL_ID", 0)
        bot_ids = getattr(cfgmod, "TRACKER_SEED_BOT_IDS", [])
        if not (guild_id and channel_id and bot_ids):
            return

        existing = await get_tracked(guild_id)
        if existing:
            return

        for bid in bot_ids:
            await add_tracked(guild_id, bid)
        await set_config(guild_id, panel_channel_id=channel_id, alert_channel_id=channel_id)

    @tasks.loop(seconds=60)
    async def auto_refresh(self):
        for guild in self.bot.guilds:
            cfg = await get_config(guild.id)
            if cfg and cfg.get("panel_channel_id") and cfg.get("panel_message_id"):
                await refresh_panel(self.bot, guild)
            elif cfg and cfg.get("panel_channel_id") and not cfg.get("panel_message_id"):
                channel = guild.get_channel(cfg["panel_channel_id"])
                if channel:
                    try:
                        msg = await channel.send(view=await build_panel_view(self.bot, guild))
                        await set_config(guild.id, panel_message_id=msg.id)
                    except discord.HTTPException:
                        pass

    @auto_refresh.before_loop
    async def before_auto_refresh(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member):
        if not after.bot:
            return
        guild = after.guild
        tracked_ids = await get_tracked(guild.id)
        if after.id not in tracked_ids:
            return
        if before.status == after.status:
            return

        await refresh_panel(self.bot, guild)

        cfg = await get_config(guild.id)
        alert_channel_id = (cfg or {}).get("alert_channel_id") or (cfg or {}).get("panel_channel_id")
        if not alert_channel_id:
            return
        channel = guild.get_channel(alert_channel_id)
        if not channel:
            return

        label = STATUS_LABEL.get(after.status, "Offline")
        status_prefix = ""
        view = ui.LayoutView()
        c = ui.Container()
        c.add_item(ui.TextDisplay(f"{status_prefix}**{after.display_name}** is now **{label}**"))
        view.add_item(c)
        try:
            await channel.send(view=view)
        except discord.HTTPException:
            pass

    @commands.group(name="tracker", invoke_without_command=True)
    @commands.guild_only()
    async def tracker_group(self, ctx: commands.Context):
        await ctx.send(view=await build_panel_view(self.bot, ctx.guild))

    @tracker_group.command(name="add")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def tracker_add(self, ctx: commands.Context, bot_member: discord.Member):
        if not bot_member.bot:
            await ctx.send(view=_status_view(False, "That member isn't a bot."))
            return
        await add_tracked(ctx.guild.id, bot_member.id)
        await refresh_panel(self.bot, ctx.guild)
        await ctx.send(view=_status_view(True, f"Now tracking **{bot_member.display_name}**."))

    @tracker_group.command(name="remove")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def tracker_remove(self, ctx: commands.Context, bot_member: discord.Member):
        await remove_tracked(ctx.guild.id, bot_member.id)
        await refresh_panel(self.bot, ctx.guild)
        await ctx.send(view=_status_view(True, f"Stopped tracking **{bot_member.display_name}**."))

    @tracker_group.command(name="panel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def tracker_panel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        msg = await target.send(view=await build_panel_view(self.bot, ctx.guild))
        await set_config(ctx.guild.id, panel_channel_id=target.id, panel_message_id=msg.id)
        if target.id != ctx.channel.id:
            await ctx.send(view=_status_view(True, f"Live panel posted in {target.mention}."))

    @tracker_group.command(name="alertchannel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def tracker_alertchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        await set_config(ctx.guild.id, alert_channel_id=channel.id)
        await ctx.send(view=_status_view(True, f"Status alerts will be sent to {channel.mention}."))

    @tracker_group.command(name="list")
    @commands.guild_only()
    async def tracker_list(self, ctx: commands.Context):
        await ctx.send(view=await build_panel_view(self.bot, ctx.guild))

    @tracker_group.command(name="refresh")
    @commands.guild_only()
    @access.action_command(manage_guild=True)
    async def tracker_refresh(self, ctx: commands.Context):
        await refresh_panel(self.bot, ctx.guild, force=True)
        await ctx.send(view=_status_view(True, "Panel refreshed."))

async def setup(bot: commands.Bot):
    await bot.add_cog(BotStatusTracker(bot))
