from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite
import discord
from discord import ui
from discord.ext import commands

from codezmanager.emojis import E as _EMGR
import config as cfgmod

MAX_CHANNELS = 3

DB_DIR = Path("db")
DB_PATH = DB_DIR / "greet.db"

VALID_MODES = ("simple", "container")

DEFAULT_SIMPLE_MSG = "Welcome {user} to **{server}**! You're member #{member_count}."
DEFAULT_TITLE = "Welcome to {server}!"
DEFAULT_DESC = "Hey {user}, welcome to **{server}**! You are member **#{member_count}**.\nEnjoy your stay!"
DEFAULT_FOOTER = "Member #{member_number} • Joined {join_time}"

_LOCAL_KEY_MAP = {"success": "SUCCESS", "error": "ERROR"}

def ES(key: str) -> str:
    return _EMGR[_LOCAL_KEY_MAP.get(key, key.upper())]

def _ensure_db():
    DB_DIR.mkdir(exist_ok=True)

async def init_db():
    _ensure_db()
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS greet_channels (
                guild_id      INTEGER NOT NULL,
                channel_id    INTEGER NOT NULL,
                mode          TEXT    DEFAULT 'container',
                content       TEXT,
                title         TEXT,
                description   TEXT,
                thumbnail_on  INTEGER DEFAULT 1,
                image_url     TEXT,
                footer_text   TEXT,
                color         INTEGER,
                autodelete    INTEGER DEFAULT 0,
                enabled       INTEGER DEFAULT 1,
                PRIMARY KEY (guild_id, channel_id)
            )
            """
        )
        await db.commit()

async def get_channels(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM greet_channels WHERE guild_id = ? ORDER BY rowid", (guild_id,)
        )
        rows = await cur.fetchall()
        return [dict(r) for r in rows]

async def get_channel_cfg(guild_id: int, channel_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM greet_channels WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

async def add_channel(guild_id: int, channel_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT OR IGNORE INTO greet_channels (guild_id, channel_id) VALUES (?, ?)",
            (guild_id, channel_id),
        )
        await db.commit()

async def remove_channel(guild_id: int, channel_id: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "DELETE FROM greet_channels WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        await db.commit()

async def update_channel(guild_id: int, channel_id: int, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [guild_id, channel_id]
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            f"UPDATE greet_channels SET {cols} WHERE guild_id = ? AND channel_id = ?", vals
        )
        await db.commit()

def _ordinal(n: int) -> str:
    s = ["th", "st", "nd", "rd"]
    v = n % 100
    return str(n) + (s[(v - 20) % 10] if 20 < v and (v - 20) % 10 < len(s) else s[v] if v < len(s) else s[0])

def _resolve_vars(template: str, member: discord.Member) -> str:
    if not template:
        return ""
    guild = member.guild
    member_count = guild.member_count or 1
    join_ts = int(member.joined_at.timestamp()) if member.joined_at else 0
    vars_map = {
        "{user}": member.mention,
        "{user_name}": member.name,
        "{user_tag}": str(member),
        "{user_id}": str(member.id),
        "{user_avatar}": str(member.display_avatar.url),
        "{server}": guild.name,
        "{server_id}": str(guild.id),
        "{server_icon}": str(guild.icon.url) if guild.icon else "",
        "{member_count}": str(member_count),
        "{member_number}": _ordinal(member_count),
        "{join_time}": f"<t:{join_ts}:F>" if join_ts else "Unknown",
    }
    for key, value in sorted(vars_map.items(), key=lambda kv: -len(kv[0])):
        template = template.replace(key, value)
    return template

VARIABLES_HELP = (
    "`{user}` mention • `{user_name}` username • `{user_tag}` name#0000\n"
    "`{user_id}` ID • `{user_avatar}` avatar URL\n"
    "`{server}` server name • `{server_id}` • `{server_icon}` icon URL\n"
    "`{member_count}` total members • `{member_number}` ordinal (1st, 2nd...)\n"
    "`{join_time}` join timestamp"
)

def _status_view(ok: bool, text: str) -> ui.LayoutView:
    view = ui.LayoutView()
    c = ui.Container()
    c.add_item(ui.TextDisplay(text))
    view.add_item(c)
    return view

def _build_simple_content(cfg: dict, member: discord.Member) -> str:
    raw = cfg.get("content") or DEFAULT_SIMPLE_MSG
    return _resolve_vars(raw, member)

def _build_container_view(cfg: dict, member: discord.Member) -> ui.LayoutView:
    title = _resolve_vars(cfg.get("title") or DEFAULT_TITLE, member)
    desc = _resolve_vars(cfg.get("description") or DEFAULT_DESC, member)
    footer = _resolve_vars(cfg.get("footer_text") or DEFAULT_FOOTER, member)
    view = ui.LayoutView(timeout=None)
    c = ui.Container()

    c.add_item(ui.TextDisplay(f"**{title}**"))
    c.add_item(ui.Separator())

    desc_display = ui.TextDisplay(desc)
    if cfg.get("thumbnail_on", 1):
        try:
            section = ui.Section(
                desc_display,
                accessory=ui.Thumbnail(media=discord.UnfurledMediaItem(url=str(member.display_avatar.url))),
            )
            c.add_item(section)
        except Exception:
            c.add_item(desc_display)
    else:
        c.add_item(desc_display)

    c.add_item(ui.Separator())

    image_raw = cfg.get("image_url")
    if image_raw:
        resolved = _resolve_vars(image_raw, member).strip()
        if resolved.startswith(("http://", "https://")):
            try:
                gallery = ui.MediaGallery()
                gallery.add_item(media=discord.UnfurledMediaItem(url=resolved))
                c.add_item(gallery)
            except Exception:
                pass

    if footer:
        c.add_item(ui.TextDisplay(f"-# {footer}"))

    view.add_item(c)
    return view

class GreetEditModal(ui.Modal, title="Edit Greet Message"):
    def __init__(self, guild_id: int, channel_id: int, cur: dict):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id

        self.content_in = ui.TextInput(
            label="Simple mode text",
            style=discord.TextStyle.paragraph,
            default=cur.get("content") or "",
            required=False,
            max_length=1500,
        )
        self.title_in = ui.TextInput(
            label="Container title",
            default=cur.get("title") or "",
            required=False,
            max_length=200,
        )
        self.desc_in = ui.TextInput(
            label="Container description",
            style=discord.TextStyle.paragraph,
            default=cur.get("description") or "",
            required=False,
            max_length=1500,
        )
        self.footer_in = ui.TextInput(
            label="Container footer",
            default=cur.get("footer_text") or "",
            required=False,
            max_length=200,
        )
        for item in (self.content_in, self.title_in, self.desc_in, self.footer_in):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await update_channel(
            self.guild_id,
            self.channel_id,
            content=self.content_in.value or None,
            title=self.title_in.value or None,
            description=self.desc_in.value or None,
            footer_text=self.footer_in.value or None,
        )
        cog: "Greet" = interaction.client.get_cog("Greet")
        await interaction.response.edit_message(view=await cog.build_panel(interaction.guild))

class GreetAppearanceModal(ui.Modal, title="Greet Appearance"):
    def __init__(self, guild_id: int, channel_id: int, cur: dict):
        super().__init__()
        self.guild_id = guild_id
        self.channel_id = channel_id

        self.image_in = ui.TextInput(
            label="Banner image URL (blank to clear)",
            default=cur.get("image_url") or "",
            required=False,
            max_length=500,
        )
        self.autodelete_in = ui.TextInput(
            label="Auto-delete after (seconds, 0 = off)",
            default=str(cur.get("autodelete") or 0),
            required=False,
            max_length=6,
        )
        for item in (self.image_in, self.autodelete_in):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        updates: dict = {"image_url": self.image_in.value.strip() or None}

        try:
            updates["autodelete"] = max(0, int(self.autodelete_in.value.strip() or 0))
        except ValueError:
            pass

        await update_channel(self.guild_id, self.channel_id, **updates)
        cog: "Greet" = interaction.client.get_cog("Greet")
        await interaction.response.edit_message(view=await cog.build_panel(interaction.guild))

class Greet(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def build_panel(self, guild: discord.Guild, selected_channel_id: int | None = None) -> ui.LayoutView:
        channels = await get_channels(guild.id)

        view = ui.LayoutView(timeout=300)
        c = ui.Container()

        c.add_item(ui.TextDisplay("**Greet Control Panel**"))
        c.add_item(ui.Separator())

        if not channels:
            c.add_item(ui.TextDisplay("No greet channels configured yet. Pick one below to add."))
        else:
            lines = []
            for row in channels:
                ch = guild.get_channel(row["channel_id"])
                status = "Enabled" if row["enabled"] else "Disabled"
                ch_label = ch.mention if ch else f"`#{row['channel_id']}`"
                extra = f" • auto-delete {row['autodelete']}s" if row["autodelete"] else ""
                lines.append(f"{status} {ch_label} — mode: `{row['mode']}`{extra}")
            c.add_item(ui.TextDisplay("\n".join(lines)))

        c.add_item(ui.Separator(visible=False))

        add_select = ui.ChannelSelect(
            placeholder=f"Add a greet channel... ({len(channels)}/{MAX_CHANNELS})",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
            disabled=len(channels) >= MAX_CHANNELS,
        )

        manage_options = [
            discord.SelectOption(label=(guild.get_channel(r["channel_id"]).name if guild.get_channel(r["channel_id"]) else str(r["channel_id"])), value=str(r["channel_id"]))
            for r in channels
        ]
        manage_select = ui.Select(
            placeholder="Manage a configured channel...",
            options=manage_options or [discord.SelectOption(label="(none configured)", value="none")],
            disabled=not manage_options,
        )

        async def _guard(interaction: discord.Interaction) -> bool:
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message(
                    view=_status_view(False, "You need **Manage Server** to use this panel."), ephemeral=True
                )
                return False
            return True

        async def on_add(interaction: discord.Interaction):
            if not await _guard(interaction):
                return
            ch_id = int(interaction.data["values"][0])
            existing = await get_channels(guild.id)
            if len(existing) >= MAX_CHANNELS:
                await interaction.response.send_message(
                    view=_status_view(False, f"Max {MAX_CHANNELS} greet channels reached."), ephemeral=True
                )
                return
            await add_channel(guild.id, ch_id)
            await interaction.response.edit_message(view=await self.build_panel(guild))

        async def on_manage(interaction: discord.Interaction):
            if not await _guard(interaction):
                return
            ch_id = int(interaction.data["values"][0])
            await interaction.response.edit_message(view=await self.build_channel_panel(guild, ch_id))

        add_select.callback = on_add
        manage_select.callback = on_manage

        c.add_item(ui.ActionRow(add_select))
        c.add_item(ui.ActionRow(manage_select))
        c.add_item(ui.TextDisplay(f"-# Use `{cfgmod.DEFAULT_PREFIX}greet variables` to see template variables"))

        view.add_item(c)
        return view

    async def build_channel_panel(self, guild: discord.Guild, channel_id: int) -> ui.LayoutView:
        cur = await get_channel_cfg(guild.id, channel_id) or {}
        ch = guild.get_channel(channel_id)
        enabled = bool(cur.get("enabled", 1))
        mode = cur.get("mode", "container")

        view = ui.LayoutView(timeout=300)
        c = ui.Container()

        c.add_item(ui.TextDisplay(f"**Configuring** {ch.mention if ch else '#unknown'}"))
        c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay(
            f"**Status:** {'Enabled' if enabled else 'Disabled'}\n"
            f"**Mode:** `{mode}`\n"
            f"**Thumbnail:** {'on' if cur.get('thumbnail_on', 1) else 'off'}\n"
            f"**Auto-delete:** {cur.get('autodelete') or 0}s"
        ))
        c.add_item(ui.Separator(visible=False))

        mode_select = ui.Select(
            placeholder=f"Mode: {mode}",
            options=[
                discord.SelectOption(label="Container (CV2)", value="container", default=(mode == "container")),
                discord.SelectOption(label="Simple (plain text)", value="simple", default=(mode == "simple")),
            ],
        )

        edit_btn = ui.Button(label="Edit Text", style=discord.ButtonStyle.primary, custom_id="gp_edit")
        appearance_btn = ui.Button(label="Appearance", style=discord.ButtonStyle.primary, custom_id="gp_app")
        thumb_btn = ui.Button(
            label="Thumbnail Off" if cur.get("thumbnail_on", 1) else "Thumbnail On",
            style=discord.ButtonStyle.secondary, custom_id="gp_thumb",
        )
        toggle_btn = ui.Button(
            label="Disable" if enabled else "Enable",
            style=discord.ButtonStyle.danger if enabled else discord.ButtonStyle.success,
            custom_id="gp_toggle",
        )
        test_btn = ui.Button(label="Test", style=discord.ButtonStyle.secondary, custom_id="gp_test")
        remove_btn = ui.Button(label="Remove Channel", style=discord.ButtonStyle.danger, custom_id="gp_remove")
        back_btn = ui.Button(label="◂ Back", style=discord.ButtonStyle.secondary, custom_id="gp_back")

        async def _guard(interaction: discord.Interaction) -> bool:
            if not interaction.user.guild_permissions.manage_guild:
                await interaction.response.send_message(
                    view=_status_view(False, "You need **Manage Server** to use this panel."), ephemeral=True
                )
                return False
            return True

        async def on_mode(interaction: discord.Interaction):
            if not await _guard(interaction):
                return
            await update_channel(guild.id, channel_id, mode=interaction.data["values"][0])
            await interaction.response.edit_message(view=await self.build_channel_panel(guild, channel_id))

        async def on_edit(interaction: discord.Interaction):
            if not await _guard(interaction):
                return
            fresh = await get_channel_cfg(guild.id, channel_id) or {}
            await interaction.response.send_modal(GreetEditModal(guild.id, channel_id, fresh))

        async def on_appearance(interaction: discord.Interaction):
            if not await _guard(interaction):
                return
            fresh = await get_channel_cfg(guild.id, channel_id) or {}
            await interaction.response.send_modal(GreetAppearanceModal(guild.id, channel_id, fresh))

        async def on_thumb(interaction: discord.Interaction):
            if not await _guard(interaction):
                return
            fresh = await get_channel_cfg(guild.id, channel_id) or {}
            await update_channel(guild.id, channel_id, thumbnail_on=0 if fresh.get("thumbnail_on", 1) else 1)
            await interaction.response.edit_message(view=await self.build_channel_panel(guild, channel_id))

        async def on_toggle(interaction: discord.Interaction):
            if not await _guard(interaction):
                return
            fresh = await get_channel_cfg(guild.id, channel_id) or {}
            await update_channel(guild.id, channel_id, enabled=0 if fresh.get("enabled", 1) else 1)
            await interaction.response.edit_message(view=await self.build_channel_panel(guild, channel_id))

        async def on_test(interaction: discord.Interaction):
            if not await _guard(interaction):
                return
            if not ch:
                await interaction.response.send_message(view=_status_view(False, "Channel no longer exists."), ephemeral=True)
                return
            fresh = await get_channel_cfg(guild.id, channel_id) or {}
            try:
                await interaction.response.defer(ephemeral=True)
                await self.send_greet(ch, interaction.user, fresh)
                await interaction.followup.send(view=_status_view(True, f"Test sent to {ch.mention}"), ephemeral=True)
            except Exception as e:
                await interaction.followup.send(view=_status_view(False, f"Failed: `{e}`"), ephemeral=True)

        async def on_remove(interaction: discord.Interaction):
            if not await _guard(interaction):
                return
            await remove_channel(guild.id, channel_id)
            await interaction.response.edit_message(view=await self.build_panel(guild))

        async def on_back(interaction: discord.Interaction):
            if not await _guard(interaction):
                return
            await interaction.response.edit_message(view=await self.build_panel(guild))

        mode_select.callback = on_mode
        edit_btn.callback = on_edit
        appearance_btn.callback = on_appearance
        thumb_btn.callback = on_thumb
        toggle_btn.callback = on_toggle
        test_btn.callback = on_test
        remove_btn.callback = on_remove
        back_btn.callback = on_back

        c.add_item(ui.ActionRow(mode_select))
        c.add_item(ui.ActionRow(edit_btn, appearance_btn, thumb_btn))
        c.add_item(ui.ActionRow(toggle_btn, test_btn, remove_btn))
        c.add_item(ui.ActionRow(back_btn))

        view.add_item(c)
        return view

    async def send_greet(self, channel: discord.abc.Messageable, member: discord.Member, cfg: dict):
        mode = cfg.get("mode", "container")
        if mode == "simple":
            msg = await channel.send(_build_simple_content(cfg, member))
        else:
            view = _build_container_view(cfg, member)
            msg = await channel.send(view=view)

        autodelete = cfg.get("autodelete") or 0
        if autodelete > 0:
            async def _delete_later():
                await asyncio.sleep(autodelete)
                try:
                    await msg.delete()
                except discord.HTTPException:
                    pass
            asyncio.create_task(_delete_later())

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        rows = await get_channels(member.guild.id)
        for row in rows:
            if not row["enabled"]:
                continue
            ch = member.guild.get_channel(row["channel_id"])
            if not ch:
                continue
            try:
                await self.send_greet(ch, member, row)
            except discord.HTTPException:
                continue

    @commands.group(name="greet", invoke_without_command=True)
    @commands.guild_only()
    async def greet_group(self, ctx: commands.Context):
        await ctx.send(view=await self.build_panel(ctx.guild))

    @greet_group.command(name="add")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def greet_add(self, ctx: commands.Context, channel: discord.TextChannel):
        existing = await get_channels(ctx.guild.id)
        if len(existing) >= MAX_CHANNELS:
            await ctx.send(view=_status_view(False, f"Max {MAX_CHANNELS} greet channels allowed."))
            return
        await add_channel(ctx.guild.id, channel.id)
        await ctx.send(view=_status_view(True, f"Added {channel.mention} as a greet channel."))

    @greet_group.command(name="remove")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def greet_remove(self, ctx: commands.Context, channel: discord.TextChannel):
        await remove_channel(ctx.guild.id, channel.id)
        await ctx.send(view=_status_view(True, f"Removed {channel.mention} from greet channels."))

    @greet_group.command(name="mode")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def greet_mode(self, ctx: commands.Context, channel: discord.TextChannel, mode: str):
        mode = mode.lower()
        if mode not in VALID_MODES:
            await ctx.send(view=_status_view(False, f"Mode must be one of: {', '.join(VALID_MODES)}"))
            return
        await update_channel(ctx.guild.id, channel.id, mode=mode)
        await ctx.send(view=_status_view(True, f"{channel.mention} greet mode set to `{mode}`."))

    @greet_group.command(name="toggle")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def greet_toggle(self, ctx: commands.Context, channel: discord.TextChannel):
        cur = await get_channel_cfg(ctx.guild.id, channel.id)
        if cur is None:
            await ctx.send(view=_status_view(False, "That channel isn't configured yet."))
            return
        new_state = 0 if cur.get("enabled", 1) else 1
        await update_channel(ctx.guild.id, channel.id, enabled=new_state)
        await ctx.send(view=_status_view(True, f"{channel.mention} greet {'enabled' if new_state else 'disabled'}."))

    @greet_group.command(name="autodelete")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def greet_autodelete(self, ctx: commands.Context, channel: discord.TextChannel, seconds: int):
        await update_channel(ctx.guild.id, channel.id, autodelete=max(0, seconds))
        await ctx.send(view=_status_view(True, f"Auto-delete for {channel.mention} set to {max(0, seconds)}s."))

    @greet_group.command(name="test")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def greet_test(self, ctx: commands.Context, channel: discord.TextChannel):
        cur = await get_channel_cfg(ctx.guild.id, channel.id)
        if cur is None:
            await ctx.send(view=_status_view(False, "That channel isn't configured yet."))
            return
        await self.send_greet(channel, ctx.author, cur)
        await ctx.send(view=_status_view(True, f"Test greet sent to {channel.mention}."))

    @greet_group.command(name="list")
    @commands.guild_only()
    async def greet_list(self, ctx: commands.Context):
        await ctx.send(view=await self.build_panel(ctx.guild))

    @greet_group.command(name="variables")
    async def greet_variables(self, ctx: commands.Context):
        view = ui.LayoutView()
        c = ui.Container()
        c.add_item(ui.TextDisplay("**Available Variables**"))
        c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay(VARIABLES_HELP))
        view.add_item(c)
        await ctx.send(view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Greet(bot))
