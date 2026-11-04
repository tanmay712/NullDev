from __future__ import annotations

import discord
from discord import ui
from discord.ext import commands

import config as cfgmod
from codezmanager import access
from codezmanager import ui as nui
from codezmanager.emojis import E


def _view(text: str, ok: bool | None = None) -> ui.LayoutView:
    """A single-container view; ``ok`` adds the NullDev tick/cross + accent."""
    return nui.simple_view(text, ok=ok)


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
                nui.lead(
                    "PERSON",
                    f"### {E.PERSON} Bot Access\n"
                    f"{E.TICK} `{p}botaccess add <@user or id>`\n"
                    f"{E.TICK} `{p}botaccess remove <@user or id>`\n"
                    f"{E.TICK} `{p}botaccess list`\n\n"
                    f"{E.INFO} People on the list can use action commands "
                    "(kick, ban, mute, warn, purge, ...).\n"
                    f"{E.WARNING} They cannot change settings or limits.",
                )
            )
        )

    @botaccess_group.command(name="add", help="Give a user access to action commands. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def botaccess_add(self, ctx: commands.Context, user: discord.User):
        if user.bot:
            await ctx.send(view=_view("You cannot give bot access to a bot account.", ok=False))
            return

        added = await access.add_access(ctx.guild.id, user.id, ctx.author.id)
        if added:
            await ctx.send(view=_view(f"{user.mention} (`{user.id}`) now has bot access.", ok=True))
        else:
            await ctx.send(view=_view(f"{user.mention} (`{user.id}`) already has bot access.", ok=False))

    @botaccess_group.command(name="remove", help="Remove a user's access to action commands. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def botaccess_remove(self, ctx: commands.Context, user: discord.User):
        removed = await access.remove_access(ctx.guild.id, user.id)
        if removed:
            await ctx.send(view=_view(f"Removed bot access from {user.mention} (`{user.id}`).", ok=True))
        else:
            await ctx.send(view=_view(f"{user.mention} (`{user.id}`) did not have bot access.", ok=False))

    @botaccess_group.command(name="list", help="List everyone with bot access. Owner only.")
    @commands.guild_only()
    @commands.is_owner()
    async def botaccess_list(self, ctx: commands.Context):
        rows = await access.list_access(ctx.guild.id)
        if not rows:
            await ctx.send(view=_view(nui.lead("WARNING", "Nobody has bot access in this server."), ok=False))
            return

        lines = [f"### {E.PERSON} Bot Access List", ""]
        for row in rows:
            uid = row["user_id"]
            lines.append(f"{E.TICK} <@{uid}> (`{uid}`) — added by <@{row['added_by']}>")
        lines.append("")
        lines.append(nui.footer_line(f"{len(rows)} user(s) with access"))
        await ctx.send(view=_view("\n".join(lines)))


async def setup(bot: commands.Bot):
    await bot.add_cog(BotAccess(bot))
