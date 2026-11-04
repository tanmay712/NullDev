from __future__ import annotations

import discord
from discord import app_commands, ui
from discord.ext import commands

from codezmanager import emoji_store

PER_PAGE = 3  # categories per page, matches the screenshot's 2-page layout


def _view(text: str) -> ui.LayoutView:
    view = ui.LayoutView()
    container = ui.Container()
    container.add_item(ui.TextDisplay(text))
    view.add_item(container)
    return view


def _build_page_text(bot_user: discord.ClientUser, pages: list[list[dict]], page: int, guild: discord.Guild) -> str:
    lines = [f"### About {bot_user.mention}", ""]

    for cat in pages[page]:
        role = guild.get_role(cat["role_id"])
        lines.append(f"**{cat['label']}**")
        if role is None:
            lines.append("*Role not found*")
        else:
            members = [m for m in role.members if not m.bot]
            if not members:
                lines.append("*Vacant*")
            else:
                for m in members:
                    lines.append(f"{m.mention}")
        lines.append("")

    lines.append(f"Page {page + 1}/{len(pages)}")
    return "\n".join(lines)


class AboutPager(ui.LayoutView):
    def __init__(self, bot_user: discord.ClientUser, guild: discord.Guild, categories: list[dict]):
        super().__init__(timeout=300)
        self.bot_user = bot_user
        self.guild = guild
        self.pages = [categories[i:i + PER_PAGE] for i in range(0, len(categories), PER_PAGE)] or [[]]
        self.page = 0

        self.container = ui.Container()
        self.text = ui.TextDisplay(self._text())
        self.container.add_item(self.text)
        self.add_item(self.container)

        self.action_row = ui.ActionRow()
        self.prev_button = ui.Button(label="\u2039", style=discord.ButtonStyle.secondary, disabled=True)
        self.next_button = ui.Button(label="\u203a", style=discord.ButtonStyle.secondary, disabled=len(self.pages) <= 1)
        self.prev_button.callback = self._go_prev
        self.next_button.callback = self._go_next
        self.action_row.add_item(self.prev_button)
        self.action_row.add_item(self.next_button)
        self.container.add_item(self.action_row)

    def _text(self) -> str:
        return _build_page_text(self.bot_user, self.pages, self.page, self.guild)

    async def _refresh(self, interaction: discord.Interaction):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page >= len(self.pages) - 1
        self.text.content = self._text()
        await interaction.response.edit_message(view=self)

    async def _go_prev(self, interaction: discord.Interaction):
        if self.page > 0:
            self.page -= 1
        await self._refresh(interaction)

    async def _go_next(self, interaction: discord.Interaction):
        if self.page < len(self.pages) - 1:
            self.page += 1
        await self._refresh(interaction)


class About(commands.Cog):
    """/about lists staff grouped into owner-defined, role-based categories."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    about_group = app_commands.Group(
        name="aboutsetup", description="Configure the /about staff categories. Owner only."
    )

    @app_commands.command(name="about", description="Show the server's staff team.")
    async def about(self, interaction: discord.Interaction):
        if interaction.guild is None:
            await interaction.response.send_message(
                view=_view("This only works inside a server."), ephemeral=True
            )
            return

        categories = await emoji_store.list_categories(interaction.guild.id)
        if not categories:
            await interaction.response.send_message(
                view=_view(
                    "No staff categories are set up yet. "
                    "An owner can add one with `/aboutsetup addcategory`."
                ),
                ephemeral=True,
            )
            return

        pager = AboutPager(self.bot.user, interaction.guild, categories)
        await interaction.response.send_message(view=pager)

    @about_group.command(name="addcategory", description="Add or update a staff category, backed by a role.")
    @app_commands.describe(
        label="Category heading shown in /about, e.g. Team, Administration, Moderation, Support",
        role="The role whose members are listed under this category",
    )
    async def addcategory(self, interaction: discord.Interaction, label: str, role: discord.Role):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                view=_view("Only the bot owner can use this command."), ephemeral=True
            )
            return

        await emoji_store.set_category(interaction.guild.id, label.strip(), role.id)
        await interaction.response.send_message(
            view=_view(f"`{label.strip()}` now lists members of {role.mention} in `/about`."),
            ephemeral=True,
        )

    @about_group.command(name="removecategory", description="Remove a staff category from /about.")
    @app_commands.describe(label="The exact category heading to remove")
    async def removecategory(self, interaction: discord.Interaction, label: str):
        if not await self.bot.is_owner(interaction.user):
            await interaction.response.send_message(
                view=_view("Only the bot owner can use this command."), ephemeral=True
            )
            return

        removed = await emoji_store.remove_category(interaction.guild.id, label.strip())
        if removed:
            await interaction.response.send_message(
                view=_view(f"Removed the `{label.strip()}` category."), ephemeral=True
            )
        else:
            await interaction.response.send_message(
                view=_view(f"No category named `{label.strip()}` was found."), ephemeral=True
            )

    @about_group.command(name="listcategories", description="List all configured /about categories.")
    async def listcategories(self, interaction: discord.Interaction):
        categories = await emoji_store.list_categories(interaction.guild.id)
        if not categories:
            await interaction.response.send_message(
                view=_view("No categories are set up yet."), ephemeral=True
            )
            return

        lines = ["### /about Categories", ""]
        for cat in categories:
            role = interaction.guild.get_role(cat["role_id"])
            role_text = role.mention if role else "*role not found*"
            lines.append(f"**{cat['label']}** -> {role_text}")
        await interaction.response.send_message(view=_view("\n".join(lines)), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(About(bot))
