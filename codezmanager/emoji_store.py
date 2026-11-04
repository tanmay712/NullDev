"""Storage for two related systems:

1. Application-emoji uploads: every custom emoji uploaded to the bot's own
   application (via /emoji upload) is recorded here AND mirrored into
   emojis.uploaded.json so the existing codezmanager.emojis.E map picks it up
   on next reload without any code changes elsewhere.

2. /about staff categories: which role fills each category shown in /about
   (Team, Administration, Moderation, Support, ... — owner-defined, not
   hardcoded), per guild.
"""
from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

DB_DIR = Path("db")
DB_PATH = DB_DIR / "emojimanager.db"

_BASE_DIR = Path(__file__).resolve().parent.parent
_UPLOADED_JSON = _BASE_DIR / "emojis.uploaded.json"


async def init_db():
    DB_DIR.mkdir(exist_ok=True)
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS app_emojis (
                slot        TEXT PRIMARY KEY,
                emoji_id    INTEGER NOT NULL,
                name        TEXT NOT NULL,
                animated    INTEGER NOT NULL DEFAULT 0,
                uploaded_by INTEGER,
                uploaded_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS about_categories (
                guild_id    INTEGER NOT NULL,
                position    INTEGER NOT NULL,
                label       TEXT NOT NULL,
                role_id     INTEGER NOT NULL,
                PRIMARY KEY (guild_id, label)
            )
            """
        )
        await db.commit()


# --------------------------------------------------------------- app emojis
async def _rewrite_uploaded_json():
    """Regenerate emojis.uploaded.json from the DB so codezmanager.emojis.E
    stays in sync without duplicating storage logic."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT slot, emoji_id, name, animated FROM app_emojis")
        rows = await cur.fetchall()

    data = {
        r["slot"]: {"id": r["emoji_id"], "name": r["name"], "animated": bool(r["animated"])}
        for r in rows
    }
    _UPLOADED_JSON.write_text(json.dumps(data, indent=2), encoding="utf-8")


async def save_emoji(slot: str, emoji_id: int, name: str, animated: bool, uploaded_by: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            INSERT INTO app_emojis (slot, emoji_id, name, animated, uploaded_by)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(slot) DO UPDATE SET
                emoji_id=excluded.emoji_id,
                name=excluded.name,
                animated=excluded.animated,
                uploaded_by=excluded.uploaded_by,
                uploaded_at=datetime('now')
            """,
            (slot, emoji_id, name, int(animated), uploaded_by),
        )
        await db.commit()
    await _rewrite_uploaded_json()

    from codezmanager.emojis import E
    E.reload()


async def remove_emoji(slot: str) -> bool:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute("DELETE FROM app_emojis WHERE slot = ?", (slot,))
        await db.commit()
        removed = cur.rowcount > 0
    if removed:
        await _rewrite_uploaded_json()
        from codezmanager.emojis import E
        E.reload()
    return removed


async def list_emojis() -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM app_emojis ORDER BY slot")
        return [dict(r) for r in await cur.fetchall()]


async def get_emoji(slot: str) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM app_emojis WHERE slot = ?", (slot,))
        row = await cur.fetchone()
        return dict(row) if row else None


# ------------------------------------------------------------ about roles
async def set_category(guild_id: int, label: str, role_id: int, position: int | None = None):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        if position is None:
            cur = await db.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM about_categories WHERE guild_id = ?",
                (guild_id,),
            )
            (position,) = await cur.fetchone()
        await db.execute(
            """
            INSERT INTO about_categories (guild_id, position, label, role_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, label) DO UPDATE SET role_id=excluded.role_id
            """,
            (guild_id, position, label, role_id),
        )
        await db.commit()


async def remove_category(guild_id: int, label: str) -> bool:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "DELETE FROM about_categories WHERE guild_id = ? AND label = ?", (guild_id, label)
        )
        await db.commit()
        return cur.rowcount > 0


async def list_categories(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM about_categories WHERE guild_id = ? ORDER BY position", (guild_id,)
        )
        return [dict(r) for r in await cur.fetchall()]
