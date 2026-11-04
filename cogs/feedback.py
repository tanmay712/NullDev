from __future__ import annotations

from pathlib import Path

import aiosqlite
import discord
from discord import ui
from discord.ext import commands

from codezmanager.emojis import E
from codezmanager.emojis import E as _EMGR
from codezmanager import ui as nui
import config as cfgmod

DB_DIR = Path("db")
DB_PATH = DB_DIR / "feedback.db"

_LOCAL_KEY_MAP = {
    "success": "SUCCESS", "error": "ERROR", "star_full": "STAR_FULL", "star_empty": "STAR_EMPTY",
}

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
            CREATE TABLE IF NOT EXISTS feedback_config (
                guild_id   INTEGER PRIMARY KEY,
                channel_id INTEGER
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS feedback_entries (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     INTEGER NOT NULL,
                user_id      INTEGER NOT NULL,
                rating       INTEGER NOT NULL,
                review       TEXT,
                screenshot   TEXT,
                created_at   INTEGER
            )
            """
        )
        await db.commit()

async def get_config(guild_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM feedback_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

async def set_channel(guild_id: int, channel_id: int | None):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO feedback_config (guild_id, channel_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET channel_id = excluded.channel_id",
            (guild_id, channel_id),
        )
        await db.commit()

async def save_entry(guild_id: int, user_id: int, rating: int, review: str, screenshot: str | None) -> int:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "INSERT INTO feedback_entries (guild_id, user_id, rating, review, screenshot, created_at) "
            "VALUES (?, ?, ?, ?, ?, strftime('%s','now'))",
            (guild_id, user_id, rating, review, screenshot),
        )
        await db.commit()
        return cur.lastrowid

def _stars(rating: int) -> str:
    rating = max(1, min(5, rating))
    return (ES("star_full") * rating) + (ES("star_empty") * (5 - rating))

def build_feedback_card(
    user: discord.abc.User,
    review: str,
    rating: int,
    screenshot: str | None = None,
) -> ui.LayoutView:
    """The feedback card: 'Feedback by <name>', quoted review, rating stars,
    avatar thumbnail, and a 'Submit a Review' button underneath."""
    view = ui.LayoutView()
    c = ui.Container()

    header = ui.TextDisplay(
        f"**Feedback by {user.display_name}**\n\n"
        f"> {review}\n\n"
        f"**Rating**\n{_stars(rating)}"
    )
    c.add_item(ui.Section(
        header,
        accessory=ui.Thumbnail(media=discord.UnfurledMediaItem(url=str(user.display_avatar.url))),
    ))
    c.add_item(ui.TextDisplay(
        f"-# {E.PERSON} {user} • `{user.id}` • <t:{int(discord.utils.utcnow().timestamp())}:R>"
    ))
    if screenshot and screenshot.startswith(("http://", "https://")):
        gallery = ui.MediaGallery()
        gallery.add_item(media=discord.UnfurledMediaItem(url=screenshot))
        c.add_item(gallery)
    view.add_item(c)

    review_btn = ui.Button(
        label="Submit a Review", style=discord.ButtonStyle.secondary,
        custom_id="fb_write_review", emoji=E.STAR or None,
    )

    async def _open_modal(i: discord.Interaction):
        await i.response.send_modal(FeedbackModal())

    review_btn.callback = _open_modal
    view.add_item(ui.ActionRow(review_btn))
    return view


class FeedbackModal(ui.Modal, title="Submit Feedback"):
    def __init__(self):
        super().__init__()
        self.rating_in = ui.TextInput(
            label="Rating (1-5)", placeholder="5", max_length=1, required=True
        )
        self.review_in = ui.TextInput(
            label="Your review", style=discord.TextStyle.paragraph, max_length=1000, required=True
        )
        self.screenshot_in = ui.TextInput(
            label="Screenshot URL (optional)", required=False, max_length=500
        )
        for item in (self.rating_in, self.review_in, self.screenshot_in):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            rating = int(self.rating_in.value.strip())
            assert 1 <= rating <= 5
        except (ValueError, AssertionError):
            await interaction.response.send_message(
                view=_status_view(False, "Rating must be a whole number from 1 to 5."), ephemeral=True
            )
            return

        cfg = await get_config(interaction.guild.id)
        if not cfg or not cfg.get("channel_id"):
            await interaction.response.send_message(
                view=_status_view(False, "Feedback isn't set up on this server yet. Ask an admin to run `feedback setchannel`."),
                ephemeral=True,
            )
            return

        channel = interaction.guild.get_channel(cfg["channel_id"])
        if not channel:
            await interaction.response.send_message(
                view=_status_view(False, "The configured feedback channel no longer exists."), ephemeral=True
            )
            return

        screenshot = self.screenshot_in.value.strip() or None
        await save_entry(interaction.guild.id, interaction.user.id, rating, self.review_in.value.strip(), screenshot)

        view = build_feedback_card(
            interaction.user, self.review_in.value.strip(), rating, screenshot
        )
        await channel.send(view=view)
        await interaction.response.send_message(
            view=_status_view(True, f"{_stars(rating)} Thanks! Your feedback was submitted."),
            ephemeral=True,
        )

class FeedbackPanelView(ui.LayoutView):

    def __init__(self):
        super().__init__(timeout=None)
        c = ui.Container(accent_colour=nui.BLURPLE)
        c.add_item(ui.TextDisplay(
            nui.lead(
                "STAR",
                f"**Share your feedback**\n"
                f"{E.STAR} Tap the button below to rate us and leave a review.\n"
                f"-# Your review is posted in the {cfgmod.BRAND_NAME} feedback channel.",
            )
        ))
        btn = ui.Button(
            label="Submit a Review", style=discord.ButtonStyle.secondary,
            custom_id="fb_write_review", emoji=E.STAR or None,
        )
        btn.callback = self.on_write
        c.add_item(ui.ActionRow(btn))
        c.add_item(ui.ActionRow(nui.support_button()))
        self.add_item(c)

    async def on_write(self, interaction: discord.Interaction):
        await interaction.response.send_modal(FeedbackModal())

class Feedback(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        self.bot.add_view(FeedbackPanelView())

    @commands.group(name="feedback", invoke_without_command=True)
    @commands.guild_only()
    async def feedback_group(self, ctx: commands.Context):
        await ctx.send(view=FeedbackPanelView())

    @feedback_group.command(name="setchannel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def feedback_setchannel(self, ctx: commands.Context, channel: discord.TextChannel):
        await set_channel(ctx.guild.id, channel.id)
        await ctx.send(view=_status_view(True, f"Feedback will now be posted in {channel.mention}."))

    @feedback_group.command(name="removechannel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def feedback_removechannel(self, ctx: commands.Context):
        await set_channel(ctx.guild.id, None)
        await ctx.send(view=_status_view(True, "Feedback channel removed."))

    @feedback_group.command(name="panel")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def feedback_panel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        await target.send(view=FeedbackPanelView())
        if target.id != ctx.channel.id:
            await ctx.send(view=_status_view(True, f"Feedback panel posted in {target.mention}."))

async def setup(bot: commands.Bot):
    await bot.add_cog(Feedback(bot))
