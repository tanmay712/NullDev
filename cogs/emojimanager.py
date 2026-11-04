from __future__ import annotations

import re

import discord
from discord import app_commands, ui
from discord.ext import commands

from codezmanager import emoji_store
from codezmanager import ui as nui
from codezmanager.emojis import E

_SLOT_RE = re.compile(r"^[A-Za-z0-9_]{2,32}$")


def _view(text: str, ok: bool | None = None) -> ui.LayoutView:
    return nui.simple_view(text, ok=ok)


class EmojiManager(commands.Cog):
    """Upload images as the bot's application emojis and wire them into
    emojis.json slots (TEAM_AVAILABLE, SUCCESS, ...) via slash commands.
    Owner only."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    emoji_group = app_commands.Group(
        name="emoji", description="Manage the bot's application emojis. Owner only."
    )

    async def cog_load(self):
        # Nothing to register here; the group is attached via decorators below.
        pass

    def _is_owner_check(self):
        async def predicate(interaction: discord.Interaction) -> bool:
            if not await self.bot.is_owner(interaction.user):
                await interaction.response.send_message(
                    view=_view(nui.lead("WARNING", "Only the bot owner can use this command."), ok=False),
                    ephemeral=True,
                )
                return False
            return True
        return app_commands.check(predicate)

    @emoji_group.command(name="upload", description="Upload an image as an application emoji and assign it to a slot.")
    @app_commands.describe(
        slot="The emojis.json key this fills, e.g. TEAM_AVAILABLE, SUCCESS, ERROR",
        name="Name for the emoji itself (letters, numbers, underscore, 2-32 chars)",
        image="The image file to upload (PNG, JPG, or GIF, under 256KB recommended)",
    )
    async def emoji_upload(
        self,
        interaction: discord.Interaction,
        slot: str,
        name: str,
        image: discord.Attachment,
    ):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                view=_view(nui.lead("WARNING", "Only the bot owner can use this command."), ok=False), ephemeral=True
            )
            return

        slot = slot.strip().upper()
        if not _SLOT_RE.match(slot):
            await interaction.response.send_message(
                view=_view("Slot names must be 2-32 characters: letters, numbers, or underscore.", ok=False),
                ephemeral=True,
            )
            return

        if not _SLOT_RE.match(name) or name[0].isdigit():
            await interaction.response.send_message(
                view=_view(
                    "Emoji name must be 2-32 characters: letters, numbers, or underscore, "
                    "and can't start with a digit.",
                    ok=False,
                ),
                ephemeral=True,
            )
            return

        if not (image.content_type or "").startswith("image/"):
            await interaction.response.send_message(
                view=_view("That attachment isn't an image.", ok=False), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            image_bytes = await image.read()
            created = await self.bot.create_application_emoji(name=name, image=image_bytes)
        except discord.HTTPException as exc:
            await interaction.followup.send(
                view=_view(f"Discord rejected the upload: `{exc.text if hasattr(exc, 'text') else exc}`", ok=False),
                ephemeral=True,
            )
            return
        except Exception as exc:
            await interaction.followup.send(
                view=_view(f"Upload failed: `{exc}`", ok=False), ephemeral=True
            )
            return

        await emoji_store.save_emoji(
            slot=slot,
            emoji_id=created.id,
            name=created.name,
            animated=created.animated,
            uploaded_by=interaction.user.id,
        )

        await interaction.followup.send(
            view=_view(
                nui.lead("SUCCESS", f"Uploaded {created} and assigned it to slot `{slot}`."),
                ok=None,
            ),
            ephemeral=True,
        )

    @emoji_group.command(name="assign", description="Point an emojis.json slot at an existing application emoji by ID.")
    @app_commands.describe(
        slot="The emojis.json key this fills, e.g. TEAM_AVAILABLE",
        emoji="Paste the existing custom emoji here",
    )
    async def emoji_assign(self, interaction: discord.Interaction, slot: str, emoji: str):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                view=_view(nui.lead("WARNING", "Only the bot owner can use this command."), ok=False), ephemeral=True
            )
            return

        slot = slot.strip().upper()
        if not _SLOT_RE.match(slot):
            await interaction.response.send_message(
                view=_view("Slot names must be 2-32 characters: letters, numbers, or underscore.", ok=False),
                ephemeral=True,
            )
            return

        m = re.match(r"^<(a)?:([A-Za-z0-9_]+):(\d+)>$", emoji.strip())
        if not m:
            await interaction.response.send_message(
                view=_view(
                    "That doesn't look like a custom emoji. Paste the emoji itself, not its name.",
                    ok=False,
                ),
                ephemeral=True,
            )
            return

        animated, name, emoji_id = bool(m.group(1)), m.group(2), int(m.group(3))
        await emoji_store.save_emoji(
            slot=slot, emoji_id=emoji_id, name=name, animated=animated, uploaded_by=interaction.user.id
        )
        await interaction.response.send_message(
            view=_view(nui.lead("SUCCESS", f"Assigned {emoji} to slot `{slot}`."), ok=None), ephemeral=True
        )

    @emoji_group.command(name="remove", description="Remove a slot's emoji assignment.")
    @app_commands.describe(slot="The emojis.json key to clear")
    async def emoji_remove(self, interaction: discord.Interaction, slot: str):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                view=_view(nui.lead("WARNING", "Only the bot owner can use this command."), ok=False), ephemeral=True
            )
            return

        slot = slot.strip().upper()
        removed = await emoji_store.remove_emoji(slot)
        if removed:
            await interaction.response.send_message(
                view=_view(nui.lead("SUCCESS", f"Removed the emoji assignment for slot `{slot}`."), ok=None),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                view=_view(f"Slot `{slot}` has no uploaded emoji assigned.", ok=False), ephemeral=True
            )

    @emoji_group.command(name="list", description="List every slot with an assigned application emoji.")
    async def emoji_list(self, interaction: discord.Interaction):
        rows = await emoji_store.list_emojis()
        if not rows:
            await interaction.response.send_message(
                view=_view(nui.lead("WARNING", "No slots have an uploaded emoji assigned yet."), ok=False),
                ephemeral=True,
            )
            return

        lines = [f"### {E.UTILITY} Assigned Emojis", ""]
        for row in rows:
            literal = f"<{'a' if row['animated'] else ''}:{row['name']}:{row['emoji_id']}>"
            lines.append(f"{E.TICK} `{row['slot']}` -> {literal} (`{row['name']}`)")
        lines.append("")
        lines.append(nui.footer_line(f"{len(rows)} slot(s) assigned"))
        await interaction.response.send_message(view=_view("\n".join(lines)), ephemeral=True)

    @emoji_group.command(name="sync", description="Delete an application emoji from Discord entirely (not just its slot).")
    @app_commands.describe(slot="The slot whose uploaded emoji should be deleted from Discord")
    async def emoji_sync_delete(self, interaction: discord.Interaction, slot: str):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                view=_view(nui.lead("WARNING", "Only the bot owner can use this command."), ok=False), ephemeral=True
            )
            return

        slot = slot.strip().upper()
        row = await emoji_store.get_emoji(slot)
        if not row:
            await interaction.response.send_message(
                view=_view(f"Slot `{slot}` has no uploaded emoji assigned.", ok=False), ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            app_emojis = await self.bot.fetch_application_emojis()
            match = discord.utils.get(app_emojis, id=row["emoji_id"])
            if match:
                await match.delete()
        except discord.HTTPException as exc:
            await interaction.followup.send(
                view=_view(f"Couldn't delete from Discord: `{exc}`", ok=False), ephemeral=True
            )
            return

        await emoji_store.remove_emoji(slot)
        await interaction.followup.send(
            view=_view(
                nui.lead("SUCCESS", f"Deleted the application emoji for slot `{slot}` and cleared the assignment."),
                ok=None,
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(EmojiManager(bot))
