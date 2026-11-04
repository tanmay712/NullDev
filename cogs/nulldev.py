"""NullDev community links.

The bot is built for the NullDev Discord: https://dc.definescloud.site
This cog is the single place that advertises it — every other panel links back
here through ``codezmanager.ui``.
"""
from __future__ import annotations

import discord
from discord import app_commands, ui
from discord.ext import commands

import config as cfgmod
from codezmanager import ui as nui
from codezmanager.emojis import E

# What the bot needs to do its job when someone invites it somewhere else.
_INVITE_PERMISSIONS = discord.Permissions(
    view_channel=True,
    send_messages=True,
    embed_links=True,
    attach_files=True,
    read_message_history=True,
    manage_messages=True,
    manage_channels=True,
    manage_roles=True,
    manage_nicknames=True,
    kick_members=True,
    ban_members=True,
    moderate_members=True,
    connect=True,
    speak=True,
    add_reactions=True,
)


def _brand_panel(bot: discord.Client) -> ui.LayoutView:
    """The NullDev card: what the server is, and a big Join button."""
    view = ui.LayoutView(timeout=None)
    c = ui.Container(accent_colour=nui.BLURPLE)

    c.add_item(ui.TextDisplay(f"# {E.NULLDEV} {cfgmod.BRAND_NAME}"))
    c.add_item(ui.TextDisplay(f"### {E.INFO} {cfgmod.SUPPORT_SERVER_URL}"))
    c.add_item(ui.Separator())

    c.add_item(ui.TextDisplay(
        f"{E.FLOWERS} **Welcome** — say hi and pick up your roles.\n"
        f"{E.GAMES} **Events & giveaways** — game nights, drops and community fun.\n"
        f"{E.PERSON} **Staff team** — meet everyone with `/about`.\n"
        f"{E.GIFT} **Support tickets** — open a private ticket whenever you need help.\n"
        f"{E.INFO} **Suggestions & feedback** — your ideas shape what gets built next.\n"
        f"{E.UTILITY} **Bot commands** — run `{cfgmod.DEFAULT_PREFIX}help` any time."
    ))
    c.add_item(ui.Separator())

    buttons = [nui.support_button("Join NullDev")]
    if bot.user is not None:
        buttons.append(
            nui.link_button(
                "Add me to your server",
                discord.utils.oauth_url(
                    bot.user.id,
                    permissions=_INVITE_PERMISSIONS,
                    scopes=("bot", "applications.commands"),
                ),
                "UTILITY",
            )
        )
    c.add_item(ui.ActionRow(*buttons))

    c.add_item(ui.TextDisplay(nui.footer_line(f"Built for {cfgmod.BRAND_NAME}")))
    view.add_item(c)
    return view


def _invite_panel(bot: discord.Client) -> ui.LayoutView:
    url = discord.utils.oauth_url(
        bot.user.id,
        permissions=_INVITE_PERMISSIONS,
        scopes=("bot", "applications.commands"),
    )
    view = ui.LayoutView(timeout=None)
    c = ui.Container(accent_colour=nui.GREEN)
    c.add_item(ui.TextDisplay(f"### {E.UTILITY} Add CodeZ Manager to your server"))
    c.add_item(ui.Separator())
    c.add_item(ui.TextDisplay(
        f"{E.TICK} Slash commands are included (`/about`, `/emoji`, `/aboutsetup`).\n"
        f"{E.TICK} Moderation, tickets, suggestions, feedback and staff panels.\n"
        f"{E.WARNING} Server Members, Message Content and Presence intents must be enabled."
    ))
    c.add_item(ui.ActionRow(nui.link_button("Invite the bot", url, "GIFT")))
    c.add_item(ui.TextDisplay(nui.footer_line(f"Questions? Join {cfgmod.BRAND_NAME}")))
    view.add_item(c)
    return view


class NullDev(commands.Cog):
    """Advertise the NullDev Discord and the bot's invite link."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(
        name="discord",
        aliases=["nulldev", "dc", "server", "community"],
        help="Get the NullDev Discord invite.",
    )
    async def discord_cmd(self, ctx: commands.Context):
        await ctx.send(view=_brand_panel(self.bot))

    @commands.command(
        name="invite",
        aliases=["botinvite", "addbot"],
        help="Get the bot's invite link.",
    )
    async def invite_cmd(self, ctx: commands.Context):
        if self.bot.user is None:
            await ctx.send(view=nui.simple_view("I'm still starting up — try again in a moment.", ok=False))
            return
        await ctx.send(view=_invite_panel(self.bot))

    @app_commands.command(name="discord", description="Get the NullDev Discord invite.")
    async def discord_slash(self, interaction: discord.Interaction):
        await interaction.response.send_message(view=_brand_panel(self.bot))


async def setup(bot: commands.Bot):
    await bot.add_cog(NullDev(bot))
