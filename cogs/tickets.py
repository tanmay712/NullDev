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
DB_PATH = DB_DIR / "tickets.db"

_LOCAL_KEY_MAP = {"success": "SUCCESS", "error": "ERROR"}

MAX_TYPES = 25  # Discord allows at most 25 options in a select menu

# Seeded the first time a panel is posted, so the dropdown works out of the box.
# (key, label, emoji slot, description)
DEFAULT_TYPES = (
    ("support", "General Support", "INFO", "Questions, help and anything else."),
    ("report", "Report a User", "WARNING", "Report a rule breaker with proof."),
    ("appeal", "Appeal a Punishment", "CROSS", "Appeal a mute, kick or ban."),
    ("partnership", "Partnership", "GIFT", "Collabs, sponsorships and partnerships."),
    ("other", "Other", "UTILITY", "Anything that doesn't fit the others."),
)

DEFAULT_NOTE = (
    "We've had way too many tickets like that.\n"
    "Please be literate and use the right category."
)


def ES(key: str) -> str:
    return _EMGR[_LOCAL_KEY_MAP.get(key, key.upper())]


def _status_view(ok: bool, text: str) -> ui.LayoutView:
    """Green + NullDev tick on success, red + NullDev cross on failure."""
    return nui.simple_view(text, ok=ok)


def _info_view(text: str) -> ui.LayoutView:
    """Neutral blue container for usage / informational messages."""
    return nui.simple_view(text, accent=nui.BLURPLE)


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
                next_number  INTEGER NOT NULL DEFAULT 1,
                panel_note   TEXT
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
                created_at INTEGER NOT NULL,
                ticket_type TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS ticket_types (
                guild_id    INTEGER NOT NULL,
                key         TEXT NOT NULL,
                label       TEXT NOT NULL,
                emoji       TEXT,
                description TEXT,
                category_id INTEGER,
                role_id     INTEGER,
                position    INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, key)
            )
            """
        )

        # Databases created by earlier versions miss these columns.
        cur = await db.execute("PRAGMA table_info(ticket_config)")
        cfg_cols = {row[1] for row in await cur.fetchall()}
        if "panel_note" not in cfg_cols:
            await db.execute("ALTER TABLE ticket_config ADD COLUMN panel_note TEXT")

        cur = await db.execute("PRAGMA table_info(tickets)")
        ticket_cols = {row[1] for row in await cur.fetchall()}
        if "ticket_type" not in ticket_cols:
            await db.execute("ALTER TABLE tickets ADD COLUMN ticket_type TEXT")

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


# ------------------------------------------------------------- ticket types
async def list_types(guild_id: int) -> list[dict]:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM ticket_types WHERE guild_id = ? ORDER BY position, key", (guild_id,)
        )
        return [dict(r) for r in await cur.fetchall()]


async def get_type(guild_id: int, key: str) -> dict | None:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM ticket_types WHERE guild_id = ? AND key = ?", (guild_id, key)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def add_type(
    guild_id: int,
    key: str,
    label: str,
    emoji: str | None = None,
    description: str | None = None,
    category_id: int | None = None,
    role_id: int | None = None,
) -> bool:
    """Add or update a ticket category. Returns True if it was new."""
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "SELECT 1 FROM ticket_types WHERE guild_id = ? AND key = ?", (guild_id, key)
        )
        existed = await cur.fetchone() is not None

        if not existed:
            cur = await db.execute(
                "SELECT COALESCE(MAX(position), -1) + 1 FROM ticket_types WHERE guild_id = ?",
                (guild_id,),
            )
            (position,) = await cur.fetchone()
        else:
            cur = await db.execute(
                "SELECT position FROM ticket_types WHERE guild_id = ? AND key = ?", (guild_id, key)
            )
            (position,) = await cur.fetchone()

        await db.execute(
            """
            INSERT INTO ticket_types (guild_id, key, label, emoji, description, category_id, role_id, position)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, key) DO UPDATE SET
                label=excluded.label,
                emoji=excluded.emoji,
                description=excluded.description,
                category_id=COALESCE(excluded.category_id, ticket_types.category_id),
                role_id=COALESCE(excluded.role_id, ticket_types.role_id)
            """,
            (guild_id, key, label, emoji, description, category_id, role_id, position),
        )
        await db.commit()
        return not existed


async def remove_type(guild_id: int, key: str) -> bool:
    async with aiosqlite.connect(str(DB_PATH)) as db:
        cur = await db.execute(
            "DELETE FROM ticket_types WHERE guild_id = ? AND key = ?", (guild_id, key)
        )
        await db.commit()
        return cur.rowcount > 0


async def seed_default_types(guild_id: int) -> list[dict]:
    """Give a guild the standard dropdown options if it has none yet."""
    existing = await list_types(guild_id)
    if existing:
        return existing
    for key, label, slot, description in DEFAULT_TYPES:
        await add_type(guild_id, key, label, emoji=E[slot] or None, description=description)
    return await list_types(guild_id)


# ------------------------------------------------------------------ tickets
async def create_ticket_record(
    channel_id: int, guild_id: int, opener_id: int, number: int, ticket_type: str | None = None
):
    async with aiosqlite.connect(str(DB_PATH)) as db:
        await db.execute(
            "INSERT INTO tickets (channel_id, guild_id, opener_id, status, number, created_at, ticket_type) "
            "VALUES (?, ?, ?, 'open', ?, strftime('%s','now'), ?)",
            (channel_id, guild_id, opener_id, number, ticket_type),
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


# -------------------------------------------------------------------- views
def _spaced_brand() -> str:
    """'NullDev' -> 'N U L L D E V', like the banner in the reference panel."""
    name = (cfgmod.BRAND_NAME or "NullDev").strip().upper()
    return " ".join(name)


def _panel_view(types: list[dict], note: str | None = None) -> ui.LayoutView:
    """The ticket panel: brand banner, warning note and a category dropdown."""
    note = (note or DEFAULT_NOTE).strip()
    view = ui.LayoutView(timeout=None)
    c = ui.Container(accent_colour=nui.BLURPLE)

    c.add_item(ui.TextDisplay(f"# {_spaced_brand()}"))
    c.add_item(ui.TextDisplay(f"> {E.GIFT} Please create tickets in the **correct category**."))
    c.add_item(ui.Separator(visible=False))

    c.add_item(ui.TextDisplay("**Read this first:**"))
    if note:
        c.add_item(ui.TextDisplay("\n".join(f"> {line}" for line in note.splitlines() if line.strip())))

    options = [
        discord.SelectOption(
            label=t["label"][:100],
            value=t["key"],
            description=(t.get("description") or None),
            emoji=(t.get("emoji") or None),
        )
        for t in types[:MAX_TYPES]
    ]
    if options:
        select = ui.Select(
            placeholder="Select a ticket category...",
            options=options,
            custom_id="codez_ticket_pick",
            min_values=1,
            max_values=1,
        )
        c.add_item(ui.ActionRow(select))

    view.add_item(c)
    return view


def _ticket_control_view(claimed: bool) -> ui.LayoutView:
    view = ui.LayoutView(timeout=None)
    c = ui.Container()
    c.add_item(ui.TextDisplay(nui.lead(
        "UTILITY", "Use the buttons below to manage this ticket." if not claimed
        else "This ticket is claimed. Use the buttons below to manage it."
    )))
    claim_btn = ui.Button(
        label="Unclaim" if claimed else "Claim",
        style=discord.ButtonStyle.secondary,
        custom_id="codez_ticket_claim",
        emoji=(E.PERSON if not claimed else E.CROSS) or None,
    )
    close_btn = ui.Button(
        label="Close Ticket", style=discord.ButtonStyle.danger,
        custom_id="codez_ticket_close", emoji=E.WARNING or None,
    )
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
        p = cfgmod.DEFAULT_PREFIX
        await ctx.send(
            view=_info_view(
                f"### {E.GIFT} Ticket Commands\n"
                f"{E.TICK} `{p}ticket panel [#channel]` — post the ticket panel.\n"
                f"{E.TICK} `{p}ticket type add <key> <label> [#category] [@role] [emoji]` — add a category.\n"
                f"{E.TICK} `{p}ticket type remove <key>` — delete a category.\n"
                f"{E.TICK} `{p}ticket type list` — show the dropdown categories.\n"
                f"{E.TICK} `{p}ticket note <line 1 | line 2>` — edit the \"Read this first\" text.\n"
                f"{E.TICK} `{p}ticket category <#category>` — fallback category for tickets.\n"
                f"{E.TICK} `{p}ticket role <@role>` — fallback support role.\n"
                f"{E.TICK} `{p}ticket logs <#channel>` — transcript log channel."
            )
        )

    @ticket_group.command(name="panel", help="Post the ticket panel in this channel.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def ticket_panel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        types = await seed_default_types(ctx.guild.id)
        cfg = await get_config(ctx.guild.id) or {}
        view = _panel_view(types, cfg.get("panel_note"))
        msg = await target.send(view=view)
        await set_config(ctx.guild.id, panel_channel_id=target.id, panel_message_id=msg.id)
        if target.id != ctx.channel.id:
            await ctx.send(view=_status_view(True, f"Ticket panel posted in {target.mention}."))

    @ticket_group.command(name="category", help="Set the fallback category for new ticket channels.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def ticket_category(self, ctx: commands.Context, category: discord.CategoryChannel):
        await set_config(ctx.guild.id, category_id=category.id)
        await ctx.send(view=_status_view(True, f"Tickets will be created under **{category.name}**."))

    @ticket_group.command(name="role", help="Set the fallback support role that can see tickets.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def ticket_role(self, ctx: commands.Context, role: discord.Role):
        await set_config(ctx.guild.id, support_role_id=role.id)
        await ctx.send(view=_status_view(True, f"Support role set to **{role.name}**."))

    @ticket_group.command(name="logs", help="Set the channel where closed ticket transcripts are posted.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def ticket_logs(self, ctx: commands.Context, channel: discord.TextChannel):
        await set_config(ctx.guild.id, log_channel_id=channel.id)
        await ctx.send(view=_status_view(True, f"Transcripts will be posted in {channel.mention}."))

    @ticket_group.command(name="note", help="Edit the 'Read this first' lines. Separate lines with |")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def ticket_note(self, ctx: commands.Context, *, text: str):
        lines = [part.strip() for part in text.split("|") if part.strip()]
        if not lines:
            await ctx.send(view=_status_view(False, "Give me at least one line of text."))
            return
        note = "\n".join(lines)
        await set_config(ctx.guild.id, panel_note=note)
        cfg = await get_config(ctx.guild.id) or {}
        if cfg.get("panel_channel_id") and cfg.get("panel_message_id"):
            channel = ctx.guild.get_channel(cfg["panel_channel_id"])
            if channel:
                try:
                    msg = await channel.fetch_message(cfg["panel_message_id"])
                    await msg.edit(view=_panel_view(await list_types(ctx.guild.id), note))
                except discord.HTTPException:
                    pass
        await ctx.send(view=_status_view(True, "Updated the panel note. Repost `ticket panel` if it didn't refresh."))

    @ticket_group.command(name="close", help="Close the current ticket channel.")
    @commands.guild_only()
    async def ticket_close_cmd(self, ctx: commands.Context):
        await self._close_ticket(ctx.channel, ctx.author)

    # ---------------------------------------------------------- type group
    @ticket_group.group(name="type", invoke_without_command=True)
    @commands.guild_only()
    async def ticket_type_group(self, ctx: commands.Context):
        p = cfgmod.DEFAULT_PREFIX
        await ctx.send(view=_info_view(
            f"### {E.GIFT} Ticket Categories\n"
            f"{E.TICK} `{p}ticket type add <key> <label> [#category] [@role] [emoji]`\n"
            f"{E.TICK} `{p}ticket type remove <key>`\n"
            f"{E.TICK} `{p}ticket type list`\n"
            f"-# Example: `{p}ticket type add bug \"Bug Report\" #Tickets-Bugs @Support`"
        ))

    @ticket_type_group.command(name="add", help="Add or update a dropdown ticket category.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def ticket_type_add(
        self,
        ctx: commands.Context,
        key: str,
        label: str,
        category: discord.CategoryChannel = None,
        role: discord.Role = None,
        emoji: str = None,
    ):
        key = "".join(ch for ch in key.lower() if ch.isalnum() or ch in "-_")[:32]
        if not key:
            await ctx.send(view=_status_view(False, "The key needs at least one letter or number."))
            return
        if len(await list_types(ctx.guild.id)) >= MAX_TYPES and not await get_type(ctx.guild.id, key):
            await ctx.send(view=_status_view(False, f"Discord only allows {MAX_TYPES} dropdown options."))
            return

        created = await add_type(
            ctx.guild.id,
            key,
            label.strip()[:100],
            emoji=emoji.strip() if emoji else None,
            category_id=category.id if category else None,
            role_id=role.id if role else None,
        )
        bits = [f"**{label.strip()}** (`{key}`)"]
        if category:
            bits.append(f"category {category.mention}")
        if role:
            bits.append(f"role {role.mention}")
        await ctx.send(view=_status_view(
            True,
            f"Ticket category {'added' if created else 'updated'}: " + " • ".join(bits),
        ))
        await self._refresh_panel(ctx.guild)

    @ticket_type_group.command(name="remove", help="Remove a dropdown ticket category.")
    @commands.guild_only()
    @commands.has_permissions(manage_guild=True)
    async def ticket_type_remove(self, ctx: commands.Context, key: str):
        removed = await remove_type(ctx.guild.id, key.lower())
        await ctx.send(view=_status_view(
            removed, f"Removed `{key.lower()}` from the ticket dropdown." if removed
            else f"No ticket category named `{key.lower()}`."
        ))
        if removed:
            await self._refresh_panel(ctx.guild)

    @ticket_type_group.command(name="list", help="Show the dropdown ticket categories.")
    @commands.guild_only()
    async def ticket_type_list(self, ctx: commands.Context):
        types = await list_types(ctx.guild.id)
        if not types:
            await ctx.send(view=_info_view(
                f"### {E.GIFT} Ticket Categories\n"
                f"{E.WARNING} None configured — `{cfgmod.DEFAULT_PREFIX}ticket panel` seeds the defaults."
            ))
            return

        lines = [f"### {E.GIFT} Ticket Categories", ""]
        for t in types:
            cat = ctx.guild.get_channel(t["category_id"]) if t["category_id"] else None
            role = ctx.guild.get_role(t["role_id"]) if t["role_id"] else None
            bits = [f"{t.get('emoji') or E.TICK} **{t['label']}** (`{t['key']}`)"]
            bits.append(f"category: {cat.mention}" if cat else "category: *fallback*")
            bits.append(f"role: {role.mention}" if role else "role: *fallback*")
            lines.append(" • ".join(bits))
        lines.append("")
        lines.append(nui.footer_line(f"{len(types)} categor(y/ies)"))
        await ctx.send(view=_info_view("\n".join(lines)))

    async def _refresh_panel(self, guild: discord.Guild):
        """Keep the posted panel's dropdown in sync after edits."""
        cfg = await get_config(guild.id) or {}
        if not (cfg.get("panel_channel_id") and cfg.get("panel_message_id")):
            return
        channel = guild.get_channel(cfg["panel_channel_id"])
        if not channel:
            return
        try:
            msg = await channel.fetch_message(cfg["panel_message_id"])
            await msg.edit(view=_panel_view(await list_types(guild.id), cfg.get("panel_note")))
        except discord.HTTPException:
            pass

    # -------------------------------------------------------- interactions
    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom_id = interaction.data.get("custom_id", "")

        if custom_id == "codez_ticket_pick":
            values = interaction.data.get("values") or []
            if values:
                await self._open_ticket(interaction, values[0])
        elif custom_id == "codez_ticket_open":
            # Panels posted before the dropdown existed still have this button.
            await self._open_ticket(interaction, None)
        elif custom_id == "codez_ticket_claim":
            await self._toggle_claim(interaction)
        elif custom_id == "codez_ticket_close":
            await interaction.response.defer()
            await self._close_ticket(interaction.channel, interaction.user)

    async def _open_ticket(self, interaction: discord.Interaction, type_key: str | None = None):
        guild = interaction.guild
        opener = interaction.user
        await interaction.response.defer(ephemeral=True, thinking=True)

        existing = await get_open_ticket_for_user(guild.id, opener.id)
        if existing:
            channel = guild.get_channel(existing["channel_id"])
            if channel:
                await interaction.followup.send(
                    view=_status_view(False, f"You already have an open ticket: {channel.mention}"),
                    ephemeral=True,
                )
                return

        cfg = await get_config(guild.id) or {}
        ticket_type = await get_type(guild.id, type_key) if type_key else None
        label = ticket_type["label"] if ticket_type else "Support"

        category = guild.get_channel((ticket_type or {}).get("category_id") or cfg.get("category_id") or 0)
        role_id = (ticket_type or {}).get("role_id") or cfg.get("support_role_id")
        support_role = guild.get_role(role_id) if role_id else None

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

        suffix = f"-{ticket_type['key']}" if ticket_type else ""
        try:
            channel = await guild.create_text_channel(
                name=f"ticket-{number:04d}{suffix}"[:100],
                category=category if isinstance(category, discord.CategoryChannel) else None,
                overwrites=overwrites,
                reason=f"Ticket opened by {opener} ({opener.id}) - {label}",
            )
        except discord.HTTPException as exc:
            await interaction.followup.send(
                view=_status_view(
                    False,
                    "I could not create the ticket channel. Check my **Manage Channels** "
                    f"permission and the category. `{exc.text or exc}`",
                ),
                ephemeral=True,
            )
            return

        await create_ticket_record(channel.id, guild.id, opener.id, number, ticket_type["key"] if ticket_type else None)

        intro = ui.LayoutView(timeout=None)
        c = ui.Container(accent_colour=nui.BLURPLE)
        mention = support_role.mention if support_role else "the support team"
        c.add_item(
            ui.TextDisplay(
                f"### {E.GIFT} Ticket #{number:04d} — {label}\n"
                f"{E.PERSON} {opener.mention} opened this ticket. {mention} will be with you shortly.\n"
                f"{E.INFO} Describe the issue with as much detail as you can.\n"
                f"{E.WARNING} Closing the ticket deletes this channel and logs a transcript."
            )
        )
        intro.add_item(c)
        await channel.send(view=intro)
        await channel.send(view=_ticket_control_view(claimed=False))

        await interaction.followup.send(
            view=_status_view(True, f"Your ticket has been created: {channel.mention}"),
            ephemeral=True,
        )

    async def _toggle_claim(self, interaction: discord.Interaction):
        ticket = await get_ticket(interaction.channel.id)
        if not ticket:
            await interaction.response.send_message(
                view=_status_view(False, "This channel is not a ticket."), ephemeral=True
            )
            return

        if ticket["claimed_by"] == interaction.user.id:
            await set_ticket_claim(interaction.channel.id, None)
            await interaction.response.edit_message(view=_ticket_control_view(claimed=False))
            await interaction.channel.send(view=_status_view(
                True, f"{interaction.user.mention} unclaimed this ticket."
            ))
        else:
            await set_ticket_claim(interaction.channel.id, interaction.user.id)
            await interaction.response.edit_message(view=_ticket_control_view(claimed=True))
            await interaction.channel.send(view=_status_view(
                True, nui.lead("PERSON", f"{interaction.user.mention} claimed this ticket.")
            ))

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
            c = ui.Container(accent_colour=nui.RED)
            c.add_item(
                ui.TextDisplay(
                    f"### {E.CROSS} Ticket #{ticket['number']:04d} closed\n"
                    f"{E.PERSON} Opened by **{opener_name}**\n"
                    f"{E.WARNING} Closed by **{closer.display_name if hasattr(closer, 'display_name') else closer}**\n"
                    f"{E.LOADING} <t:{int(discord.utils.utcnow().timestamp())}:F>"
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
