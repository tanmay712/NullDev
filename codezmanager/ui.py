"""Shared NullDev UI helpers.

Every panel and status message in the bot is built through these so the
NullDev emoji set — defined in ``emojis.json`` and loaded by
``codezmanager.emojis`` — is applied consistently everywhere.

The emojis are literals like ``<a:tick_tick:123>`` that live in the NullDev
Discord (https://dc.definescloud.site). ``lead()`` degrades gracefully: if a
slot is blank the text is returned untouched instead of leaving a stray space.
"""
from __future__ import annotations

from typing import Optional

import discord
from discord import ui

import config as cfgmod
from codezmanager.emojis import E

# Brand-ish accents used on the CV2 containers.
GREEN = discord.Colour.from_str("#57F287")
RED = discord.Colour.from_str("#ED4245")
YELLOW = discord.Colour.from_str("#FEE75C")
BLURPLE = discord.Colour.from_str("#5865F2")
GREY = discord.Colour.from_str("#2B2D31")


def lead(key: str, text: str) -> str:
    """Prefix ``text`` with the emoji stored in slot ``key``."""
    emoji = E[key]
    return f"{emoji} {text}" if emoji else text


# Discord member status -> emoji slot
_STATUS_KEYS = {
    discord.Status.online: "ONLINE",
    discord.Status.idle: "IDLE",
    discord.Status.dnd: "DND",
    discord.Status.offline: "OFFLINE",
    discord.Status.invisible: "OFFLINE",
}


def status_key(status: Optional[discord.Status]) -> str:
    return _STATUS_KEYS.get(status, "OFFLINE")


def status_emoji(status: Optional[discord.Status]) -> str:
    """The NullDev emoji for a presence status (online / idle / dnd / offline)."""
    return E[status_key(status)]


def simple_view(text: str, ok: Optional[bool] = None, accent: Optional[discord.Colour] = None) -> ui.LayoutView:
    """One-container view with a single line of text.

    ``ok=True`` paints it green with a tick, ``ok=False`` red with a cross,
    ``ok=None`` leaves the text alone (useful for informational panels).
    """
    if ok is not None:
        text = lead("SUCCESS" if ok else "ERROR", text)
        accent = GREEN if ok else RED

    view = ui.LayoutView()
    view.add_item(ui.Container(ui.TextDisplay(text), accent_colour=accent))
    return view


def link_button(label: str, url: str, key: Optional[str] = None) -> ui.Button:
    """A link-style button, optionally prefixed with an emoji."""
    return ui.Button(
        style=discord.ButtonStyle.link,
        label=label,
        url=url,
        emoji=(E[key] or None) if key else None,
    )


def support_button(label: Optional[str] = None) -> ui.Button:
    """The standard 'Join NullDev' link button."""
    return link_button(label or f"Join {cfgmod.BRAND_NAME}", cfgmod.SUPPORT_SERVER_URL, "NULLDEV")


def brand_line(extra: Optional[str] = None) -> str:
    """Small footer line pointing at the NullDev Discord."""
    line = lead("NULLDEV", f"**{cfgmod.BRAND_NAME}** — {cfgmod.SUPPORT_SERVER_URL}")
    return f"{line}\n-# {extra}" if extra else line


def footer_line(extra: str) -> str:
    """Subtext footer with the NullDev link appended."""
    emoji = E.HOME
    tail = f"{emoji} {extra} • {cfgmod.SUPPORT_SERVER_URL}" if emoji else f"{extra} • {cfgmod.SUPPORT_SERVER_URL}"
    return f"-# {tail}"
