from __future__ import annotations

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
DB_PATH = DB_DIR / "suggestions.db"
STATUS_LABELS = {
    "pending": "Pending",
    "approved": "Approved",
    "denied": "Denied",
    "considered": "Under Consideration",
}

# NullDev emoji shown next to each suggestion status.
STATUS_EMOJI = {
    "pending": E.LOADING,
    "approved": E.TICK,
    "denied": E.CROSS,
    "considered": E.INFO,
}

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
            CREATE TABLE IF NOT EXISTS suggestion_config (
                guild_id       INTEGER PRIMARY KEY,
                channel_id     INTEGER,
                log_channel_id INTEGER,
                vote_threshold INTEGER
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS suggestions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id    INTEGER NOT NULL,
                message_id  INTEGER,
                channel_id  INTEGER,
                author_id   INTEGER NOT NULL,
                text        TEXT NOT NULL,
                status      TEXT DEFAULT 'pending',
                mod_note    TEXT,
                created_at  INTEGER
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS suggestion_votes (
                suggestion_id INTEGER NOT NULL,
                user_id       INTEGER NOT NULL,
                vote_type     TEXT NOT NULL,
                PRIMARY KEY (suggestion_id, user_id)
            )
            """
        )
        await db.commit()

async def get_config(guild_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM suggestion_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def set_config(guild_id: int, **fields):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO suggestion_config (guild_id) VALUES (?) ON CONFLICT(guild_id) DO NOTHING", (guild_id,)
        )
        if fields:
            cols = ", ".join(f"{k} = ?" for k in fields)
            await db.execute(
                f"UPDATE suggestion_config SET {cols} WHERE guild_id = ?", list(fields.values()) + [guild_id]
            )
        await db.commit()

async def create_suggestion(guild_id: int, author_id: int, text: str) -> int:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "INSERT INTO suggestions (guild_id, author_id, text, created_at) VALUES (?, ?, ?, strftime('%s','now'))",
            (guild_id, author_id, text),
        )
        await db.commit()
        return cur.lastrowid

async def attach_message(suggestion_id: int, channel_id: int, message_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "UPDATE suggestions SET channel_id = ?, message_id = ? WHERE id = ?",
            (channel_id, message_id, suggestion_id),
        )
        await db.commit()

async def get_suggestion_by_message(message_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM suggestions WHERE message_id = ?", (message_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def get_suggestion(suggestion_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM suggestions WHERE id = ?", (suggestion_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def set_status(suggestion_id: int, status: str, mod_note: str | None):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "UPDATE suggestions SET status = ?, mod_note = ? WHERE id = ?", (status, mod_note, suggestion_id)
        )
        await db.commit()

async def cast_vote(suggestion_id: int, user_id: int, vote_type: str) -> str:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT vote_type FROM suggestion_votes WHERE suggestion_id = ? AND user_id = ?",
            (suggestion_id, user_id),
        )
        row = await cur.fetchone()
        if row is None:
            await db.execute(
                "INSERT INTO suggestion_votes (suggestion_id, user_id, vote_type) VALUES (?, ?, ?)",
                (suggestion_id, user_id, vote_type),
            )
            result = "added"
        elif row["vote_type"] == vote_type:
            await db.execute(
                "DELETE FROM suggestion_votes WHERE suggestion_id = ? AND user_id = ?",
                (suggestion_id, user_id),
            )
            result = "removed"
        else:
            await db.execute(
                "UPDATE suggestion_votes SET vote_type = ? WHERE suggestion_id = ? AND user_id = ?",
                (vote_type, suggestion_id, user_id),
            )
            result = "changed"
        await db.commit()
        return result

async def get_vote_counts(suggestion_id: int) -> tuple[int, int]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "SELECT vote_type, COUNT(*) FROM suggestion_votes WHERE suggestion_id = ? GROUP BY vote_type",
            (suggestion_id,),
        )
        rows = await cur.fetchall()
        counts = {t: n for t, n in rows}
        return counts.get("up", 0), counts.get("down", 0)

async def build_suggestion_container(bot: commands.Bot, suggestion: dict) -> ui.LayoutView:
    up, down = await get_vote_counts(suggestion["id"])
    status = suggestion.get("status", "pending")
    author = bot.get_user(suggestion["author_id"])
    author_label = str(author) if author else f"User {suggestion['author_id']}"
    avatar_url = str(author.display_avatar.url) if author else None

    view = ui.LayoutView(timeout=None)
    c = ui.Container()

    author_name = author.display_name if author else f"User {suggestion['author_id']}"
    header = ui.TextDisplay(
        f"**Suggested by {author_name}**\n\n> {suggestion['text']}"
    )
    if avatar_url:
        c.add_item(ui.Section(header, accessory=ui.Thumbnail(media=discord.UnfurledMediaItem(url=avatar_url))))
    else:
        c.add_item(header)

    status_icon = STATUS_EMOJI.get(status, E.INFO)
    if suggestion.get("mod_note"):
        c.add_item(ui.TextDisplay(f"> {E.INFO} **Mod note:** {suggestion['mod_note']}"))

    c.add_item(ui.Separator(visible=False))
    c.add_item(ui.TextDisplay("**Cast Your Vote Below!**"))

    up_btn = ui.Button(
        label=f"Support ({up})", style=discord.ButtonStyle.success,
        custom_id="sugg_upvote", emoji=E.TICK or None,
    )
    down_btn = ui.Button(
        label=f"Oppose ({down})", style=discord.ButtonStyle.danger,
        custom_id="sugg_downvote", emoji=E.CROSS or None,
    )

    async def _up_cb(interaction: discord.Interaction):
        await _handle_suggestion_vote(interaction, "up")

    async def _down_cb(interaction: discord.Interaction):
        await _handle_suggestion_vote(interaction, "down")

    up_btn.callback = _up_cb
    down_btn.callback = _down_cb

    c.add_item(ui.ActionRow(up_btn, down_btn))
    c.add_item(ui.TextDisplay(
        f"-# {E.PERSON} {author_label} • {status_icon} {STATUS_LABELS.get(status, status)} • "
        f"<t:{suggestion.get('created_at') or 0}:R>"
    ))

    view.add_item(c)
    return view

async def _handle_suggestion_vote(interaction: discord.Interaction, vote_type: str):
    suggestion = await get_suggestion_by_message(interaction.message.id)
    if not suggestion:
        await interaction.response.send_message(
            view=_status_view(False, "This suggestion is no longer tracked."),
            ephemeral=True,
        )
        return
    await cast_vote(suggestion["id"], interaction.user.id, vote_type)
    fresh = await get_suggestion(suggestion["id"])
    new_view = await build_suggestion_container(interaction.client, fresh)
    await interaction.response.edit_message(view=new_view)

class SuggestionVoteRouter(ui.LayoutView):

    def __init__(self):
        super().__init__(timeout=None)
        c = ui.Container()
        up_btn = ui.Button(
            label="Support", style=discord.ButtonStyle.success,
            custom_id="sugg_upvote", emoji=E.TICK or None,
        )
        down_btn = ui.Button(
            label="Oppose", style=discord.ButtonStyle.danger,
            custom_id="sugg_downvote", emoji=E.CROSS or None,
        )
        up_btn.callback = self.on_upvote
        down_btn.callback = self.on_downvote
        c.add_item(ui.ActionRow(up_btn, down_btn))
        self.add_item(c)

    async def on_upvote(self, interaction: discord.Interaction):
        await _handle_suggestion_vote(interaction, "up")

    async def on_downvote(self, interaction: discord.Interaction):
        await _handle_suggestion_vote(interaction, "down")

class Suggestions(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        await init_db()
        self.bot.add_view(SuggestionVoteRouter())

    async def post_suggestion(self, guild: discord.Guild, channel: discord.TextChannel, author: discord.abc.User, text: str):
        suggestion_id = await create_suggestion(guild.id, author.id, text)
        suggestion = await get_suggestion(suggestion_id)
        view = await build_suggestion_container(self.bot, suggestion)
        msg = await channel.send(view=view)
        await attach_message(suggestion_id, channel.id, msg.id)

        try:
            thread = await msg.create_thread(
                name=f"{author.display_name} - Suggestion"[:100],
                auto_archive_duration=1440,
            )
            await thread.send(nui.lead(
                "STAR", f"{author.mention} submitted a new suggestion. Discuss it here!"
            ))
        except discord.HTTPException:
            pass

        return msg

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        cfg = await get_config(message.guild.id)
        if not cfg or not cfg.get("channel_id") or message.channel.id != cfg["channel_id"]:
            return
        if not message.content.strip():
            return
        try:
            await message.delete()
        except discord.HTTPException:
            pass
        await self.post_suggestion(message.guild, message.channel, message.author, message.content.strip())

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        if interaction.response.is_done():
            return

        custom_id = interaction.data.get("custom_id", "")
        if custom_id == "sugg_upvote":
            await _handle_suggestion_vote(interaction, "up")
        elif custom_id == "sugg_downvote":
            await _handle_suggestion_vote(interaction, "down")

    @commands.group(name="suggest", invoke_without_command=True)
    @commands.guild_only()
    async def suggest_group(self, ctx: commands.Context, *, text: str = None):
        if text is None:
            await ctx.send_help(ctx.command)
            return
        cfg = await get_config(ctx.guild.id)
        channel = ctx.guild.get_channel(cfg["channel_id"]) if cfg and cfg.get("channel_id") else ctx.channel
        await self.post_suggestion(ctx.guild, channel, ctx.author, text)
        if channel.id != ctx.channel.id:
            await ctx.send(view=_status_view(True, f"Suggestion posted in {channel.mention}."))
        else:
            try:
                await ctx.message.delete()
            except discord.HTTPException:
                pass

    @suggest_group.command(name="setchannel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def suggest_setchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        await set_config(ctx.guild.id, channel_id=channel.id)
        await ctx.send(view=_status_view(True, f"Suggestion channel set to {channel.mention}. Messages posted there become suggestion cards automatically."))

    @suggest_group.command(name="removechannel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def suggest_removechannel(self, ctx: commands.Context):
        await set_config(ctx.guild.id, channel_id=None)
        await ctx.send(view=_status_view(True, "Suggestion channel removed."))

    @suggest_group.command(name="logchannel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def suggest_logchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        await set_config(ctx.guild.id, log_channel_id=channel.id)
        await ctx.send(view=_status_view(True, f"Suggestion log channel set to {channel.mention}."))

    @suggest_group.command(name="threshold")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def suggest_threshold(self, ctx: commands.Context, upvotes: int):
        await set_config(ctx.guild.id, vote_threshold=max(0, upvotes))
        await ctx.send(view=_status_view(True, f"Log threshold set to {max(0, upvotes)} upvotes."))

    @suggest_group.command(name="moderate")
    @commands.guild_only()
    @access.action_command(manage_messages=True)
    async def suggest_moderate(self, ctx: commands.Context, message_id: int, status: str, *, note: str = None):
        status = status.lower()
        if status not in STATUS_LABELS:
            await ctx.send(view=_status_view(False, f"Status must be one of: {', '.join(STATUS_LABELS)}"))
            return
        suggestion = await get_suggestion_by_message(message_id)
        if not suggestion:
            await ctx.send(view=_status_view(False, "No tracked suggestion with that message ID."))
            return
        await set_status(suggestion["id"], status, note)
        fresh = await get_suggestion(suggestion["id"])
        channel = ctx.guild.get_channel(fresh["channel_id"])
        if channel:
            try:
                msg = await channel.fetch_message(fresh["message_id"])
                await msg.edit(view=await build_suggestion_container(self.bot, fresh))
            except discord.HTTPException:
                pass
        await ctx.send(view=_status_view(
            True,
            f"Suggestion #{suggestion['id']} marked {STATUS_EMOJI.get(status, '')} "
            f"**{STATUS_LABELS[status]}**.",
        ))

async def setup(bot: commands.Bot):
    await bot.add_cog(Suggestions(bot))
