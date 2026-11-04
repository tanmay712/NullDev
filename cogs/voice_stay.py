from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path

import aiosqlite
import discord
from discord import ui
from discord.ext import commands
from discord.utils import utcnow

from codezmanager.emojis import E
from codezmanager.emojis import E as _EMGR
from codezmanager import access
from codezmanager import ui as nui
import config as cfgmod

DB_DIR = Path("db")
DB_PATH = DB_DIR / "voice_stay.db"

RECONNECT_ATTEMPTS = 3
RECONNECT_DELAY = 5
KICK_LOOKBACK = timedelta(seconds=15)

_LOCAL_KEY_MAP = {"success": "SUCCESS", "error": "ERROR"}

def ES(key: str) -> str:
    return _EMGR[_LOCAL_KEY_MAP.get(key, key.upper())]

def _status_view(ok: bool, text: str) -> ui.LayoutView:
    return nui.simple_view(text, ok=ok)

def _ensure_db():
    DB_DIR.mkdir(exist_ok=True)

async def init_db():
    _ensure_db()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS voice_lock (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                active     INTEGER DEFAULT 1
            )
            """
        )
        await db.commit()

async def set_lock(guild_id: int, channel_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO voice_lock (guild_id, channel_id, active) VALUES (?, ?, 1) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id, active = 1",
            (guild_id, channel_id),
        )
        await db.commit()

async def clear_lock(guild_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("UPDATE voice_lock SET active = 0 WHERE guild_id = ?", (guild_id,))
        await db.commit()

async def get_lock(guild_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM voice_lock WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def get_all_active() -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM voice_lock WHERE active = 1")
        return [dict(r) for r in await cur.fetchall()]

class VoiceStay(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._reconnected_after_start = False
        self._reconnecting_guilds: set[int] = set()

    @commands.Cog.listener()
    async def on_ready(self):
        if self._reconnected_after_start:
            return
        self._reconnected_after_start = True

        for lock in await get_all_active():
            guild = self.bot.get_guild(lock["guild_id"])
            if not guild:
                continue
            channel = guild.get_channel(lock["channel_id"])
            if not isinstance(channel, discord.VoiceChannel) or guild.voice_client:
                continue
            try:
                await channel.connect(reconnect=True)
            except discord.ClientException:
                pass

    async def _was_disconnected_by_mod(self, guild: discord.Guild) -> bool:
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.member_disconnect):
                if utcnow() - entry.created_at <= KICK_LOOKBACK:
                    return True
        except (discord.Forbidden, discord.HTTPException):
            pass
        return False

    async def _attempt_reconnect(self, guild: discord.Guild, channel_id: int):
        if guild.id in self._reconnecting_guilds:
            return
        self._reconnecting_guilds.add(guild.id)
        try:
            for attempt in range(RECONNECT_ATTEMPTS):
                await asyncio.sleep(RECONNECT_DELAY)
                lock = await get_lock(guild.id)
                if not lock or not lock["active"] or guild.voice_client:
                    return
                channel = guild.get_channel(channel_id)
                if not isinstance(channel, discord.VoiceChannel):
                    await clear_lock(guild.id)
                    return
                try:
                    await channel.connect(reconnect=True)
                    return
                except discord.ClientException:
                    continue
        finally:
            self._reconnecting_guilds.discard(guild.id)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.id != self.bot.user.id:
            return
        if not (before.channel is not None and after.channel is None):
            return

        guild = member.guild
        lock = await get_lock(guild.id)
        if not lock or not lock["active"]:
            return

        if await self._was_disconnected_by_mod(guild):
            await clear_lock(guild.id)
            return

        asyncio.create_task(self._attempt_reconnect(guild, lock["channel_id"]))

    @commands.command(name="join")
    @commands.guild_only()
    @access.action_command(manage_guild=True)
    @commands.bot_has_permissions(connect=True, speak=True)
    async def join(self, ctx: commands.Context, channel: discord.VoiceChannel = None):
        channel = channel or (ctx.author.voice.channel if ctx.author.voice else None)
        if channel is None:
            await ctx.send(view=_status_view(False, "Join a voice channel first, or pass one: `Cz!join #vc`."))
            return

        vc = ctx.guild.voice_client
        try:
            if vc:
                await vc.move_to(channel)
            else:
                await channel.connect(reconnect=True)
        except discord.ClientException as e:
            await ctx.send(view=_status_view(False, f"Couldn't join: `{e}`"))
            return

        await set_lock(ctx.guild.id, channel.id)
        await ctx.send(view=_status_view(
            True,
            f"{E.ONLINE} Joined {channel.mention} and staying until kicked or `Cz!leave`.",
        ))

    @commands.command(name="leave", aliases=["disconnect", "vcleave"])
    @commands.guild_only()
    @access.action_command(manage_guild=True)
    async def leave(self, ctx: commands.Context):
        await clear_lock(ctx.guild.id)
        vc = ctx.guild.voice_client
        if vc:
            await vc.disconnect(force=True)
            await ctx.send(view=_status_view(True, f"{E.OFFLINE} Left the voice channel."))
        else:
            await ctx.send(view=_status_view(False, "I'm not in a voice channel here."))

async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceStay(bot))
