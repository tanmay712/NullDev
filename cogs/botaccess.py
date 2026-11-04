from __future__ import annotations

import discord
from discord import ui
from discord.ext import commands

import config as cfgmod
from codezmanager import access


def _view(text: str) -> ui.LayoutView:
    """A plain container with a single text block. No colour, no emojis."""
    view = ui.LayoutView()
    container = ui.Container()
    container.add_item(ui.TextDisplay(text))
    view.add_item(container)
    return view


class BotAccess(commands.Cog):
    """Manage who is allowed to use action commands. Owner only."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.group(name="botaccess", invoke_without_command=True, help="Manage bot access. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def botaccess_group(self, ctx: commands.Context):
        p = cfgmod.DEFAULT_PREFIX
        await ctx.send(
            view=_view(
                "### Bot Access\n"
                f"`{p}botaccess add <@user or id>`\n"
                f"`{p}botaccess remove <@user or id>`\n"
                f"`{p}botaccess list`\n\n"
                "People on the list can use action commands (kick, ban, mute, warn, purge, ...). "
                "They cannot change settings or limits."
            )
        )

    @botaccess_group.command(name="add", help="Give a user access to action commands. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def botaccess_add(self, ctx: commands.Context, user: discord.User):
        if user.bot:
            await ctx.send(view=_view("You cannot give bot access to a bot account."))
            return

        added = await access.add_access(ctx.guild.id, user.id, ctx.author.id)
        if added:
            await ctx.send(view=_view(f"{user.mention} (`{user.id}`) now has bot access."))
        else:
            await ctx.send(view=_view(f"{user.mention} (`{user.id}`) already has bot access."))

    @botaccess_group.command(name="remove", help="Remove a user's access to action commands. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def botaccess_remove(self, ctx: commands.Context, user: discord.User):
        removed = await access.remove_access(ctx.guild.id, user.id)
        if removed:
            await ctx.send(view=_view(f"Removed bot access from {user.mention} (`{user.id}`)."))
        else:
            await ctx.send(view=_view(f"{user.mention} (`{user.id}`) did not have bot access."))

    @botaccess_group.command(name="list", help="List everyone with bot access. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def botaccess_list(self, ctx: commands.Context):
        rows = await access.list_access(ctx.guild.id)
        if not rows:
            await ctx.send(view=_view("Nobody has bot access in this server."))
            return

        lines = ["### Bot Access List", ""]
        for row in rows:
            uid = row["user_id"]
            lines.append(f"<@{uid}> (`{uid}`) - added by <@{row['added_by']}>")
        await ctx.send(view=_view("\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(BotAccess(bot))
