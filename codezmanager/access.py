"""Bot-access whitelist.

Users on this list can run *action* commands (kick, ban, mute, warn, ...) even
without the matching Discord permission. They can NOT run any command that
changes a setting or a limit. Those stay owner / Discord-permission only.

Usage on an action command (replaces @commands.has_permissions(...)):

    @commands.guild_only()
    @access.action_command(kick_members=True)
"""
from __future__ import annotations

from pathlib import Path

import aiosqlite
from discord.ext import commands

DB_DIR = Path("db")
DB_PATH = DB_DIR / "botaccess.db"


async def init_db():
    DB_DIR.mkdir(exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS bot_access (
                guild_id INTEGER NOT NULL,
                user_id  INTEGER NOT NULL,
                added_by INTEGER NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )
        await db.commit()


async def add_access(guild_id: int, user_id: int, added_by: int) -> bool:
    """Returns True if newly added, False if the user already had access."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "INSERT INTO bot_access (guild_id, user_id, added_by) VALUES (?, ?, ?) "
            "ON CONFLICT(guild_id, user_id) DO NOTHING",
            (guild_id, user_id, added_by),
        )
        await db.commit()
        return cur.rowcount > 0


async def remove_access(guild_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "DELETE FROM bot_access WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        await db.commit()
        return cur.rowcount > 0


async def list_access(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM bot_access WHERE guild_id = ?", (guild_id,))
        return [dict(r) for r in await cur.fetchall()]


async def has_access(guild_id: int, user_id: int) -> bool:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "SELECT 1 FROM bot_access WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
        )
        return await cur.fetchone() is not None


def action_command(**perms: bool):
    """Like @commands.has_permissions(**perms), but whitelisted users also pass.

    Order of checks:
      1. Bot owner            -> pass
      2. On the access list   -> pass
      3. Has the Discord perm -> pass
      4. Otherwise            -> MissingPermissions (same error as before)
    """

    async def predicate(ctx: commands.Context) -> bool:
        if ctx.guild is None:
            raise commands.NoPrivateMessage()

        if await ctx.bot.is_owner(ctx.author):
            return True

        if await has_access(ctx.guild.id, ctx.author.id):
            return True

        resolved = ctx.channel.permissions_for(ctx.author)
        missing = [p for p, needed in perms.items() if needed and not getattr(resolved, p, False)]
        if not missing:
            return True
        raise commands.MissingPermissions(missing)

    return commands.check(predicate)
