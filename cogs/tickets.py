from __future__ import annotations

from pathlib import Path

import aiosqlite
import discord
from discord import ui
from discord.ext import commands

from codezmanager.emojis import E as _EMGR
import config as cfgmod

DB_DIR = Path("db")
DB_PATH = DB_DIR / "tickets.db"

_LOCAL_KEY_MAP = {"success": "SUCCESS", "error": "ERROR"}


def ES(key: str) -> str:
    return _EMGR[_LOCAL_KEY_MAP.get(key, key.upper())]


def _status_view(text: str) -> ui.LayoutView:
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
            CREATE TABLE IF NOT EXISTS ticket_config (
                guild_id     INTEGER PRIMARY KEY,
                category_id  INTEGER,
                support_role_id INTEGER,
                log_channel_id  INTEGER,
                panel_channel_id INTEGER,
                panel_message_id INTEGER,
                next_number  INTEGER NOT NULL DEFAULT 1
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                channel_id INTEGER PRIMARY KEY,
                guild_id   INTEGER NOT NULL,
                opener_id  INTEGER NOT NULL,
                claimed_by INTEGER,
                status     TEXT NOT NULL DEFAULT 'open',
                number     INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            )
            """
        )
        await db.commit()


async def get_config(guild_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM ticket_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_config(guild_id: int, **fields):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO ticket_config (guild_id) VALUES (?) ON CONFLICT(guild_id) DO NOTHING", (guild_id,)
        )
        if fields:
            cols = ", ".join(f"{k} = ?" for k in fields)
            await db.execute(
                f"UPDATE ticket_config SET {cols} WHERE guild_id = ?", list(fields.values()) + [guild_id]
            )
        await db.commit()


async def next_ticket_number(guild_id: int) -> int:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO ticket_config (guild_id) VALUES (?) ON CONFLICT(guild_id) DO NOTHING", (guild_id,)
        )
        cur = await db.execute("SELECT next_number FROM ticket_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        number = row[0] if row else 1
        await db.execute(
            "UPDATE ticket_config SET next_number = ? WHERE guild_id = ?", (number + 1, guild_id)
        )
        await db.commit()
        return number


async def create_ticket_record(channel_id: int, guild_id: int, opener_id: int, number: int):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO tickets (channel_id, guild_id, opener_id, status, number, created_at) "
            "VALUES (?, ?, ?, 'open', ?, strftime('%s','now'))",
            (channel_id, guild_id, opener_id, number),
        )
        await db.commit()


async def get_ticket(channel_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def set_ticket_claim(channel_id: int, claimed_by: int | None):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (claimed_by, channel_id))
        await db.commit()


async def set_ticket_status(channel_id: int, status: str):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute("UPDATE tickets SET status = ? WHERE channel_id = ?", (status, channel_id))
        await db.commit()


async def get_open_ticket_for_user(guild_id: int, user_id: int) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM tickets WHERE guild_id = ? AND opener_id = ? AND status = 'open'",
            (guild_id, user_id),
        )
        row = await cur.fetchone()
        return dict(row) if row else None


def _panel_view() -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)
    c = ui.Container()
    c.add_item(ui.TextDisplay("### Support Tickets\nNeed help? Click below to open a private ticket with staff."))
    c.add_item(ui.Separator())
    button = ui.Button(label="Open Ticket", style=discord.ButtonStyle.primary, custom_id="codez_ticket_open")
    c.add_item(ui.ActionRow(button))
    view.add_item(c)
    return view


def _ticket_control_view(claimed: bool) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)
    c = ui.Container()
    c.add_item(ui.TextDisplay("Use the buttons below to manage this ticket."))
    claim_btn = ui.Button(
        label="Unclaim" if claimed else "Claim",
        style=discord.ButtonStyle.secondary,
        custom_id="codez_ticket_claim",
    )
    close_btn = ui.Button(label="Close Ticket", style=discord.ButtonStyle.danger, custom_id="codez_ticket_close")
    c.add_item(ui.ActionRow(claim_btn, close_btn))
    view.add_item(c)
    return view


class Tickets(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # -------------------------------------------------------------- panel
    @commands.group(name="ticket", invoke_without_command=True)
    @commands.guild_only()
    async def ticket_group(self, ctx: commands.Context):
        await ctx.send(
            view=_status_view(
                f"`{cfgmod.DEFAULT_PREFIX}ticket panel` — post the ticket panel here.\n"
                f"`{cfgmod.DEFAULT_PREFIX}ticket category <#category>` — set where ticket channels are created.\n"
                f"`{cfgmod.DEFAULT_PREFIX}ticket role <@role>` — set the support role that can see tickets.\n"
                f"`{cfgmod.DEFAULT_PREFIX}ticket logs <#channel>` — set the transcript log channel."
            )
        )

    @ticket_group.command(name="panel", help="Post the ticket panel in this channel.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def ticket_panel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        msg = await target.send(view=_panel_view())
        await set_config(ctx.guild.id, panel_channel_id=target.id, panel_message_id=msg.id)
        if target.id != ctx.channel.id:
            await ctx.send(view=_status_view(f"Ticket panel posted in {target.mention}."))

    @ticket_group.command(name="category", help="Set the category where new ticket channels are created.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def ticket_category(self, ctx: commands.Context, category: discord.CategoryChannel):
        await set_config(ctx.guild.id, category_id=category.id)
        await ctx.send(view=_status_view(f"Tickets will be created under **{category.name}**."))

    @ticket_group.command(name="role", help="Set the support role that can view and manage tickets.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def ticket_role(self, ctx: commands.Context, role: discord.Role):
        await set_config(ctx.guild.id, support_role_id=role.id)
        await ctx.send(view=_status_view(f"Support role set to **{role.name}**."))

    @ticket_group.command(name="logs", help="Set the channel where closed ticket transcripts are posted.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def ticket_logs(self, ctx: commands.Context, channel: discord.TextChannel):
        await set_config(ctx.guild.id, log_channel_id=channel.id)
        await ctx.send(view=_status_view(f"Transcripts will be posted in {channel.mention}."))

    @ticket_group.command(name="close", help="Close the current ticket channel.")
    @commands.guild_only()
    async def ticket_close_cmd(self, ctx: commands.Context):
        await self._close_ticket(ctx.channel, ctx.author)

    # -------------------------------------------------------- interactions
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")
        if custom_id == "codez_ticket_open":
            await self._open_ticket(interaction)
        elif custom_id == "codez_ticket_claim":
            await self._toggle_claim(interaction)
        elif custom_id == "codez_ticket_close":
            await interaction.response.defer()
            await self._close_ticket(interaction.channel, interaction.user)

    async def _open_ticket(self, interaction: discord.Interaction):
        guild = interaction.guild
        opener = interaction.user

        existing = await get_open_ticket_for_user(guild.id, opener.id)
        if existing:
            channel = guild.get_channel(existing["channel_id"])
            if channel:
                await interaction.response.send_message(
                    f"You already have an open ticket: {channel.mention}", ephemeral=True
                )
                return

        cfg = await get_config(guild.id) or {}
        category = guild.get_channel(cfg.get("category_id")) if cfg.get("category_id") else None
        support_role = guild.get_role(cfg.get("support_role_id")) if cfg.get("support_role_id") else None

        number = await next_ticket_number(guild.id)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            opener: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True),
        }
        if support_role:
            overwrites[support_role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{number:04d}",
                category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites,
                reason=f"Ticket opened by {opener} ({opener.id})",
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "I do not have permission to create ticket channels.", ephemeral=True
            )
            return

        await create_ticket_record(channel.id, guild.id, opener.id, number)

        intro = ui.LayoutView(timeout=None)
        c = ui.Container()
        mention = support_role.mention if support_role else "the support team"
        c.add_item(
            ui.TextDisplay(
                f"### Ticket #{number:04d}\n{opener.mention} opened this ticket. {mention} will be with you shortly."
            )
        )
        intro.add_item(c)
        await channel.send(view=intro)
        await channel.send(view=_ticket_control_view(claimed=False))

        await interaction.response.send_message(f"Your ticket has been created: {channel.mention}", ephemeral=True)

    async def _toggle_claim(self, interaction: discord.Interaction):
        ticket = await get_ticket(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message("This channel is not a ticket.", ephemeral=True)
            return

        if ticket["claimed_by"] == interaction.user.id:
            await set_ticket_claim(interaction.channel.id, None)
            await interaction.response.edit_message(view=_ticket_control_view(claimed=False))
            await interaction.channel.send(view=_status_view(f"{interaction.user.mention} unclaimed this ticket."))
        else:
            await set_ticket_claim(interaction.channel.id, interaction.user.id)
            await interaction.response.edit_message(view=_ticket_control_view(claimed=True))
            await interaction.channel.send(view=_status_view(f"{interaction.user.mention} claimed this ticket."))

    async def _close_ticket(self, channel: discord.abc.GuildChannel, closer: discord.abc.User):
        ticket = await get_ticket(channel.id)
        if not ticket:
            return

        await set_ticket_status(channel.id, "closed")

        guild = channel.guild
        cfg = await get_config(guild.id) or {}
        log_channel = guild.get_channel(cfg.get("log_channel_id")) if cfg.get("log_channel_id") else None

        if log_channel:
            opener = guild.get_member(ticket["opener_id"])
            opener_name = opener.display_name if opener else f"ID {ticket['opener_id']}"
            lines = []
            try:
                async for msg in channel.history(limit=500, oldest_first=True):
                    stamp = msg.created_at.strftime("%Y-%m-%d %H:%M")
                    content = msg.content or "[no text content]"
                    lines.append(f"[{stamp}] {msg.author}: {content}")
            except discord.HTTPException:
                pass

            transcript = "\n".join(lines) if lines else "No messages were sent."
            import io

            buffer = io.BytesIO(transcript.encode("utf-8"))
            file = discord.File(buffer, filename=f"ticket-{ticket['number']:04d}-transcript.txt")

            summary = ui.LayoutView()
            c = ui.Container()
            c.add_item(
                ui.TextDisplay(
                    f"### Ticket #{ticket['number']:04d} closed\n"
                    f"Opened by **{opener_name}**\n"
                    f"Closed by **{closer.display_name if hasattr(closer, 'display_name') else closer}**"
                )
            )
            summary.add_item(c)
            try:
                await log_channel.send(view=summary, file=file)
            except discord.HTTPException:
                pass

        try:
            await channel.delete(reason=f"Ticket closed by {closer}")
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Tickets(bot))
