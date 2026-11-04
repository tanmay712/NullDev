import discord
from discord.ext import commands
from discord import ui
from discord.http import Route
import aiosqlite
import asyncio
import time
import io
import traceback
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from codezmanager.emojis import E as _EMGR
import re as _re

_LOCAL_KEY_MAP = {"success": "SUCCESS", "error": "ERROR"}

def ES(key: str) -> str:
    return _EMGR[_LOCAL_KEY_MAP.get(key, key.upper())]

BOT_NAME     = "CodeZ Manager"

DB_DIR   = Path("db")
DB_PATH  = DB_DIR / "tag.db"
FONT_DIR = Path("assets/fonts")

FONTS = [
    {"id": 1,  "name": "Bangers",       "file": "Bangers-Regular.ttf",       "desc": "DEPRECATED by Discord - may 400"},
    {"id": 2,  "name": "BioRhyme",      "file": "BioRhyme-Regular.ttf",      "desc": "DEPRECATED by Discord - may 400"},
    {"id": 3,  "name": "Cherry Bomb",   "file": "CherryBomb-Regular.ttf",    "desc": "Sakura - playful bubble"},
    {"id": 4,  "name": "Chicle",        "file": "Chicle-Regular.ttf",        "desc": "Jellybean - rounded soft"},
    {"id": 5,  "name": "Compagnon",     "file": "Compagnon-Bold.otf",        "desc": "DEPRECATED by Discord - may 400"},
    {"id": 6,  "name": "Museo Moderno", "file": "MuseoModerno-Regular.ttf",  "desc": "Modern display"},
    {"id": 7,  "name": "Neo-Castel",    "file": "Neo-castel.ttf",            "desc": "Medieval - gothic"},
    {"id": 8,  "name": "Pixelify Sans", "file": "PixelifySans-Regular.ttf",  "desc": "8Bit - retro pixel"},
    {"id": 9,  "name": "Ribes",         "file": "Ribes-Black.otf",           "desc": "DEPRECATED by Discord - may 400"},
    {"id": 10, "name": "Sinistre",      "file": "Sinistre.otf",              "desc": "Vampyre - dark elegant"},
    {"id": 11, "name": "Default",       "file": "gg sans Bold.ttf",          "desc": "Standard Discord (gg Sans)"},
    {"id": 12, "name": "Zilla Slab",    "file": "ZillaSlab-Regular.ttf",     "desc": "Tempo - slab-serif"},
    {"id": 13, "name": "Monkey Bars",   "file": "MonkeyBars-Regular.ttf",    "desc": "NEW - Playpen Sans, playful"},
    {"id": 14, "name": "Mainframe",     "file": "Mainframe-Regular.ttf",     "desc": "NEW - Orbitron, techy"},
    {"id": 15, "name": "Headbang",      "file": "Headbang-Regular.ttf",      "desc": "NEW - New Rocker, grungy"},
    {"id": 16, "name": "Journal",       "file": "Journal-Regular.ttf",       "desc": "NEW - Kalam, handwritten"},
]

EFFECTS = [
    {"id": 1, "name": "Solid",    "desc": "Displays the first color"},
    {"id": 2, "name": "Gradient", "desc": "Two color gradient"},
    {"id": 3, "name": "Neon",     "desc": "Glow around the name"},
    {"id": 4, "name": "Toon",     "desc": "Vertical gradient + stroke"},
    {"id": 5, "name": "Pop",      "desc": "Colored drop shadow"},
    {"id": 6, "name": "Glow",     "desc": "Alternate gradient style"},
    {"id": 7, "name": "Prism",    "desc": "NEW - scrolling 5-color gradient"},
    {"id": 8, "name": "Gummy",    "desc": "NEW - 4-color squash/stretch letters"},
]

COLORS = [
    {"name": "Red & Black",    "p": 0xFF0000, "s": 0x000000},
    {"name": "Blue & Gold",    "p": 0x0066FF, "s": 0xFFD700},
    {"name": "Purple & Pink",  "p": 0x8B00FF, "s": 0xFF69B4},
    {"name": "Pastel Pink",    "p": 0xFFCCE7, "s": 0xD33FDD},
    {"name": "Green & Black",  "p": 0x00FF00, "s": 0x000000},
    {"name": "Cyan & Blue",    "p": 0x00FFFF, "s": 0x0000FF},
    {"name": "Gold & White",   "p": 0xFFD700, "s": 0xFFFFFF},
    {"name": "Orange & Red",   "p": 0xFF8C00, "s": 0xFF0000},
    {"name": "White & Black",  "p": 0xFFFFFF, "s": 0x000000},
    {"name": "Sunset",         "p": 0xFF4500, "s": 0xFF8C00},
    {"name": "Ocean",          "p": 0x006994, "s": 0x00CED1},
    {"name": "Forest",         "p": 0x228B22, "s": 0x006400},
    {"name": "Lavender",       "p": 0xE6E6FA, "s": 0x9370DB},
    {"name": "Rose Gold",      "p": 0xB76E79, "s": 0xF0E68C},
    {"name": "Ice Blue",       "p": 0xA5F2F3, "s": 0x4169E1},
    {"name": "Fire",           "p": 0xFF4500, "s": 0xFFD700},
    {"name": "Midnight",       "p": 0x191970, "s": 0x4B0082},
    {"name": "Cotton Candy",   "p": 0xFFBCD9, "s": 0xA2D2FF},
    {"name": "Neon Green",     "p": 0x39FF14, "s": 0x00FF00},
    {"name": "Blood Moon",     "p": 0x8B0000, "s": 0xDC143C},
    {"name": "Arctic",         "p": 0xF0F8FF, "s": 0x87CEEB},
    {"name": "Royal",          "p": 0x4169E1, "s": 0xFFD700},
    {"name": "Toxic",          "p": 0x7FFF00, "s": 0xADFF2F},
    {"name": "Sakura",         "p": 0xFFB7C5, "s": 0xFF69B4},
    {"name": "Galaxy",         "p": 0x4B0082, "s": 0x8A2BE2},
]

PRESETS = [
    {"name": "Gaming",  "font_id": 1,  "effect_id": 3, "ci": 0},
    {"name": "Anime",   "font_id": 3,  "effect_id": 6, "ci": 23},
    {"name": "Dev",     "font_id": 5,  "effect_id": 1, "ci": 4},
    {"name": "Minimal", "font_id": 11, "effect_id": 1, "ci": 8},
    {"name": "Gothic",  "font_id": 7,  "effect_id": 3, "ci": 16},
    {"name": "Luxury",  "font_id": 2,  "effect_id": 2, "ci": 13},
    {"name": "Galaxy",  "font_id": 6,  "effect_id": 6, "ci": 24},
    {"name": "Retro",   "font_id": 8,  "effect_id": 5, "ci": 9},
    {"name": "Dark",    "font_id": 10, "effect_id": 3, "ci": 19},
    {"name": "Neon",    "font_id": 1,  "effect_id": 3, "ci": 18},
    {"name": "Pastel",  "font_id": 4,  "effect_id": 2, "ci": 3},
    {"name": "Royal",   "font_id": 12, "effect_id": 4, "ci": 21},
]

def dec_to_hex(dec: int) -> str:
    return f"#{dec:06X}"

def hex_to_dec(hex_str: str) -> int | None:
    clean = hex_str.replace("#", "").strip().upper()
    if len(clean) != 6:
        return None
    try:
        return int(clean, 16)
    except ValueError:
        return None

def is_valid_hex(s: str) -> bool:
    clean = s.replace("#", "").strip()
    if len(clean) != 6:
        return False
    try:
        int(clean, 16)
        return True
    except ValueError:
        return False

def dec_to_rgb(dec: int) -> tuple:
    return ((dec >> 16) & 0xFF, (dec >> 8) & 0xFF, dec & 0xFF)

def get_font_by_id(fid: int) -> dict:
    for f in FONTS:
        if f["id"] == fid:
            return f
    return FONTS[10]

def get_effect_by_id(eid: int) -> dict:
    for e in EFFECTS:
        if e["id"] == eid:
            return e
    return EFFECTS[0]

def _load_pil_font(font_file: str, size: int) -> ImageFont.FreeTypeFont:
    path = FONT_DIR / font_file
    try:
        if path.exists():
            return ImageFont.truetype(str(path), size)
        else:
            print(f"[Tag] Missing font file: {path}")
    except Exception as e:
        print(f"[Tag] Font load fail {font_file}: {e}")
    for fb in ("arial.ttf", "Arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(fb, size)
        except Exception:
            continue
    return ImageFont.load_default()

def _draw_gradient_text(canvas: Image.Image, xy: tuple, text: str,
                        font: ImageFont.FreeTypeFont, c1: tuple, c2: tuple):
    x, y = xy
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    if tw <= 0 or th <= 0:
        return

    pad = 20
    W = tw + pad * 2
    H = th + pad * 2

    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=255)

    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad_px = grad.load()
    for gx in range(W):
        t = gx / max(W - 1, 1)
        r = int(c1[0] * (1 - t) + c2[0] * t)
        g = int(c1[1] * (1 - t) + c2[1] * t)
        b = int(c1[2] * (1 - t) + c2[2] * t)
        for gy in range(H):
            grad_px[gx, gy] = (r, g, b, 255)
    grad.putalpha(mask)
    canvas.paste(grad, (x - pad, y - pad), grad)

def _draw_multicolor_gradient_text(canvas: Image.Image, xy: tuple, text: str,
                                    font: ImageFont.FreeTypeFont, colors: list):
    x, y = xy
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    if tw <= 0 or th <= 0 or len(colors) < 2:
        return

    pad = 20
    W = tw + pad * 2
    H = th + pad * 2

    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).text((pad - bbox[0], pad - bbox[1]), text, font=font, fill=255)

    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    grad_px = grad.load()
    segments = len(colors) - 1
    for gx in range(W):
        t = gx / max(W - 1, 1)
        seg = min(int(t * segments), segments - 1)
        local_t = (t * segments) - seg
        c1, c2 = colors[seg], colors[seg + 1]
        r = int(c1[0] * (1 - local_t) + c2[0] * local_t)
        g = int(c1[1] * (1 - local_t) + c2[1] * local_t)
        b = int(c1[2] * (1 - local_t) + c2[2] * local_t)
        for gy in range(H):
            grad_px[gx, gy] = (r, g, b, 255)
    grad.putalpha(mask)
    canvas.paste(grad, (x - pad, y - pad), grad)

def _draw_gummy_text(canvas: Image.Image, xy: tuple, text: str,
                      font: ImageFont.FreeTypeFont, c1: tuple, c2: tuple):
    x, y = xy
    draw = ImageDraw.Draw(canvas)
    cx = x
    for i, ch in enumerate(text):
        col = c1 if i % 2 == 0 else c2
        draw.text((cx, y), ch, font=font, fill=col + (255,))
        cw = font.getlength(ch)
        cx += cw

def generate_preview(nickname: str, font_id: int, effect_id: int,
                     primary: int, secondary: int) -> io.BytesIO:
    W, H = 900, 280
    bg_color = (47, 49, 54, 255)

    canvas = Image.new("RGBA", (W, H), bg_color)

    font_info = get_font_by_id(font_id)
    effect_info = get_effect_by_id(effect_id)

    text = nickname or "Preview"
    font_size = 120
    pil_font = _load_pil_font(font_info["file"], font_size)

    while pil_font.getlength(text) > W - 100 and font_size > 30:
        font_size -= 4
        pil_font = _load_pil_font(font_info["file"], font_size)

    bbox = pil_font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = (W - tw) // 2 - bbox[0]
    ty = (H - th) // 2 - bbox[1] - 20

    c1 = dec_to_rgb(primary)
    c2 = dec_to_rgb(secondary)

    effect_name = effect_info["name"]

    if effect_name == "Solid":
        draw = ImageDraw.Draw(canvas)
        draw.text((tx, ty), text, font=pil_font, fill=c1 + (255,))

    elif effect_name == "Gradient":
        _draw_gradient_text(canvas, (tx, ty), text, pil_font, c1, c2)

    elif effect_name == "Neon":
        glow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        gd.text((tx, ty), text, font=pil_font, fill=c1 + (200,))

        blurred1 = glow_layer.filter(ImageFilter.GaussianBlur(radius=15))
        blurred2 = glow_layer.filter(ImageFilter.GaussianBlur(radius=8))
        canvas = Image.alpha_composite(canvas, blurred1)
        canvas = Image.alpha_composite(canvas, blurred1)
        canvas = Image.alpha_composite(canvas, blurred2)

        draw = ImageDraw.Draw(canvas)
        for dx in range(-3, 4):
            for dy in range(-3, 4):
                if dx * dx + dy * dy <= 9 and (dx or dy):
                    draw.text((tx + dx, ty + dy), text, font=pil_font, fill=c2 + (255,))
        draw.text((tx, ty), text, font=pil_font, fill=c1 + (255,))

    elif effect_name == "Toon":
        draw = ImageDraw.Draw(canvas)
        outline_col = (0, 0, 0, 255)
        stroke = 5
        for dx in range(-stroke, stroke + 1):
            for dy in range(-stroke, stroke + 1):
                if dx * dx + dy * dy <= stroke * stroke and (dx or dy):
                    draw.text((tx + dx, ty + dy), text, font=pil_font, fill=outline_col)
        _draw_gradient_text(canvas, (tx, ty), text, pil_font, c1, c2)

    elif effect_name == "Pop":
        shadow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow_layer)
        offset = 8
        sd.text((tx + offset, ty + offset), text, font=pil_font, fill=c2 + (255,))
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(radius=3))
        canvas = Image.alpha_composite(canvas, shadow_layer)
        draw = ImageDraw.Draw(canvas)
        draw.text((tx, ty), text, font=pil_font, fill=c1 + (255,))

    elif effect_name == "Glow":
        glow_layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        gd = ImageDraw.Draw(glow_layer)
        gd.text((tx, ty), text, font=pil_font, fill=c2 + (255,))
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(radius=20))
        canvas = Image.alpha_composite(canvas, glow_layer)
        canvas = Image.alpha_composite(canvas, glow_layer)
        draw = ImageDraw.Draw(canvas)
        draw.text((tx, ty), text, font=pil_font, fill=c1 + (255,))

    elif effect_name == "Gummy":
        _draw_gummy_text(canvas, (tx, ty), text, pil_font, c1, c2)

    elif effect_name == "Prism":
        stops = []
        for i in range(5):
            t = i / 4
            r = int(c1[0] * (1 - t) + c2[0] * t)
            g = int(c1[1] * (1 - t) + c2[1] * t)
            b = int(c1[2] * (1 - t) + c2[2] * t)
            stops.append((r, g, b))
        _draw_multicolor_gradient_text(canvas, (tx, ty), text, pil_font, stops)

    footer_font = _load_pil_font("gg sans Bold.ttf", 20)
    footer_text = f"Font: {font_info['name']}  -  Effect: {effect_info['name']}  -  {dec_to_hex(primary)} > {dec_to_hex(secondary)}"
    fw = footer_font.getlength(footer_text)
    ImageDraw.Draw(canvas).text(
        ((W - fw) // 2, H - 36), footer_text,
        font=footer_font, fill=(185, 187, 190, 255)
    )

    buf = io.BytesIO()
    canvas.convert("RGB").save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return buf

def _error_view(text: str) -> ui.LayoutView:
    v = ui.LayoutView()
    c = ui.Container()
    c.add_item(ui.TextDisplay(text))
    v.add_item(c)
    return v

def _success_view(text: str) -> ui.LayoutView:
    v = ui.LayoutView()
    c = ui.Container()
    c.add_item(ui.TextDisplay(text))
    v.add_item(c)
    return v

def _info_view(text: str) -> ui.LayoutView:
    v = ui.LayoutView()
    c = ui.Container()
    c.add_item(ui.TextDisplay(text))
    v.add_item(c)
    return v

def build_colors_for_effect(effect_id: int, primary: int, secondary: int) -> list:
    if effect_id in (2, 6, 7, 8):
        return [primary, secondary]
    return [primary]

async def apply_display_style(bot, guild_id, nick, font_id, effect_id, colors):
    try:
        body = {
            "display_name_font_id": font_id,
            "display_name_effect_id": effect_id,
            "display_name_colors": colors,
        }
        if nick is not None:
            body["nick"] = nick
        route = Route("PATCH", "/guilds/{guild_id}/members/@me", guild_id=guild_id)
        await bot.http.request(route, json=body)
        return {"success": True}
    except discord.HTTPException as e:
        return {"success": False, "error": str(e), "code": e.code, "status": e.status}
    except Exception as e:
        traceback.print_exc()
        return {"success": False, "error": str(e), "code": None, "status": None}

async def clear_display_style(bot, guild_id):
    try:
        body = {
            "nick": None,
            "display_name_font_id": None,
            "display_name_effect_id": None,
            "display_name_colors": None,
        }
        route = Route("PATCH", "/guilds/{guild_id}/members/@me", guild_id=guild_id)
        await bot.http.request(route, json=body)
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

def format_error(result: dict) -> str:
    msg = result.get("error", "Unknown error")
    code = result.get("code")
    status = result.get("status")
    if code == 50013: return "Missing permissions."
    if code == 50035: return f"Invalid values.\n`{msg}`"
    if code == 429:   return "Rate limited."
    if status == 403: return "Forbidden."
    if status == 404: return "Endpoint unavailable."
    if status == 400: return f"Bad request.\n`{msg}`"
    return f"`{msg}`"

def build_main_view(cog, guild_id: int, state: dict) -> tuple:
    view = TagView(cog, guild_id, state)
    c = ui.Container()

    nick    = state.get("nickname", BOT_NAME)
    font    = get_font_by_id(state.get("font_id", 11))
    effect  = get_effect_by_id(state.get("effect_id", 1))
    prim    = state.get("primary_color", 0xFFFFFF)
    sec     = state.get("secondary_color", 0x000000)
    preset  = state.get("selected_preset", "None")
    updated = state.get("updated_at")

    updated_str = f"<t:{updated}:R>" if updated else "`Never`"

    c.add_item(ui.TextDisplay(f"### {nick} Name Style"))
    c.add_item(ui.Separator())

    file = None
    try:
        buf = generate_preview(nick, font["id"], effect["id"], prim, sec)
        file = discord.File(buf, filename="preview.png")
        gallery = ui.MediaGallery()
        gallery.add_item(media="attachment://preview.png")
        c.add_item(gallery)
    except Exception as e:
        print(f"[Tag] Preview gen failed: {e}")
        traceback.print_exc()
        c.add_item(ui.TextDisplay(f"Preview unavailable: `{e}`"))

    c.add_item(ui.TextDisplay(
        f"**Font:** `{font['name']}`   "
        f"**Effect:** `{effect['name']}`\n"
        f"**Colors:** `{dec_to_hex(prim)}` → `{dec_to_hex(sec)}`"
    ))
    c.add_item(ui.Separator())

    c.add_item(ui.ActionRow(view.font_select))
    c.add_item(ui.ActionRow(view.effect_select))
    c.add_item(ui.ActionRow(view.color_select))
    c.add_item(ui.ActionRow(view.preset_select))

    r_actions = ui.ActionRow()
    r_actions.add_item(view.btn_apply)
    r_actions.add_item(view.btn_hex)
    r_actions.add_item(view.btn_edit)
    r_actions.add_item(view.btn_reset)
    r_actions.add_item(view.btn_close)
    c.add_item(r_actions)

    c.add_item(ui.Separator(visible=False))
    c.add_item(ui.TextDisplay(
        f"-# {BOT_NAME} - Preset: `{preset}` - Last Applied: {updated_str}\n"
        f"-# Changes update preview instantly. Press **Apply** to save to Discord."
    ))

    view.add_item(c)
    return view, file

class TagView(ui.LayoutView):
    def __init__(self, cog, guild_id: int, state: dict):
        super().__init__(timeout=300)
        self.cog       = cog
        self.guild_id  = guild_id
        self.state     = state
        self.author_id = state.get("_author_id")

        font_options = []
        for f in FONTS:
            font_options.append(discord.SelectOption(
                label=f["name"],
                value=str(f["id"]),
                description=f["desc"][:100],
                default=(f["id"] == state.get("font_id", 11)),
            ))
        current_font = get_font_by_id(state.get('font_id', 11))
        self.font_select = ui.Select(
            placeholder=f"Font: {current_font['name']}",
            options=font_options,
            custom_id="t_font_sel",
            min_values=1, max_values=1,
        )
        self.font_select.callback = self._on_font_select

        effect_options = []
        for e in EFFECTS:
            effect_options.append(discord.SelectOption(
                label=e["name"],
                value=str(e["id"]),
                description=e["desc"][:100],
                default=(e["id"] == state.get("effect_id", 1)),
            ))
        current_effect = get_effect_by_id(state.get('effect_id', 1))
        self.effect_select = ui.Select(
            placeholder=f"Effect: {current_effect['name']}",
            options=effect_options,
            custom_id="t_effect_sel",
            min_values=1, max_values=1,
        )
        self.effect_select.callback = self._on_effect_select

        color_options = []
        for i, cl in enumerate(COLORS):
            color_options.append(discord.SelectOption(
                label=cl["name"],
                value=str(i),
                description=f"{dec_to_hex(cl['p'])} to {dec_to_hex(cl['s'])}",
            ))
        self.color_select = ui.Select(
            placeholder="Choose Color Preset (25 available)",
            options=color_options[:25],
            custom_id="t_color_sel",
            min_values=1, max_values=1,
        )
        self.color_select.callback = self._on_color_select

        preset_options = []
        for i, p in enumerate(PRESETS):
            f = get_font_by_id(p["font_id"])
            e = get_effect_by_id(p["effect_id"])
            preset_options.append(discord.SelectOption(
                label=p["name"],
                value=str(i),
                description=f"{f['name']} + {e['name']}"[:100],
                default=(p["name"] == state.get("selected_preset")),
            ))
        self.preset_select = ui.Select(
            placeholder="Load Style Preset (12 available)",
            options=preset_options,
            custom_id="t_preset_sel",
            min_values=1, max_values=1,
        )
        self.preset_select.callback = self._on_preset_select

        self.btn_apply = ui.Button(label="Apply",       style=discord.ButtonStyle.success,   custom_id="t_apply")
        self.btn_hex   = ui.Button(label="Custom Hex",  style=discord.ButtonStyle.primary,   custom_id="t_hex")
        self.btn_edit  = ui.Button(label="Edit Name",   style=discord.ButtonStyle.primary,   custom_id="t_edit")
        self.btn_reset = ui.Button(label="Reset",       style=discord.ButtonStyle.danger,    custom_id="t_reset")
        self.btn_close = ui.Button(label="Close",       style=discord.ButtonStyle.secondary, custom_id="t_close")

        self.btn_apply.callback = self._on_apply
        self.btn_hex.callback   = self._on_hex
        self.btn_edit.callback  = self._on_edit
        self.btn_reset.callback = self._on_reset
        self.btn_close.callback = self._on_close

    async def _check(self, interaction: discord.Interaction) -> bool:
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message(
                view=_error_view("Only the command user can use this!"),
                ephemeral=True,
            )
            return False
        return True

    async def _refresh(self, interaction: discord.Interaction):
        try:
            new_view, new_file = build_main_view(self.cog, self.guild_id, self.state)
            kwargs = {"view": new_view}
            if new_file:
                kwargs["attachments"] = [new_file]
            await interaction.message.edit(**kwargs)
        except Exception as e:
            print(f"[Tag] Refresh error: {e}")
            traceback.print_exc()

    async def _wait_input(self, interaction: discord.Interaction, timeout: float = 30.0):
        def check(m):
            return m.author.id == interaction.user.id and m.channel.id == interaction.channel.id
        try:
            msg = await self.cog.bot.wait_for("message", check=check, timeout=timeout)
        except asyncio.TimeoutError:
            return None
        try:
            await msg.delete()
        except Exception:
            pass
        return msg.content.strip()

    async def _on_font_select(self, interaction: discord.Interaction):
        if not await self._check(interaction): return
        self.state["font_id"] = int(self.font_select.values[0])
        self.state["selected_preset"] = "Custom"
        await interaction.response.defer()
        await self._refresh(interaction)

    async def _on_effect_select(self, interaction: discord.Interaction):
        if not await self._check(interaction): return
        self.state["effect_id"] = int(self.effect_select.values[0])
        self.state["selected_preset"] = "Custom"
        await interaction.response.defer()
        await self._refresh(interaction)

    async def _on_color_select(self, interaction: discord.Interaction):
        if not await self._check(interaction): return
        idx = int(self.color_select.values[0])
        cp = COLORS[idx]
        self.state["primary_color"] = cp["p"]
        self.state["secondary_color"] = cp["s"]
        self.state["selected_preset"] = "Custom"
        await interaction.response.defer()
        await self._refresh(interaction)

    async def _on_preset_select(self, interaction: discord.Interaction):
        if not await self._check(interaction): return
        idx = int(self.preset_select.values[0])
        p = PRESETS[idx]
        self.state["font_id"] = p["font_id"]
        self.state["effect_id"] = p["effect_id"]
        cl = COLORS[p["ci"]]
        self.state["primary_color"] = cl["p"]
        self.state["secondary_color"] = cl["s"]
        self.state["selected_preset"] = p["name"]
        await interaction.response.defer()
        await self._refresh(interaction)

    async def _on_apply(self, interaction: discord.Interaction):
        if not await self._check(interaction): return
        await interaction.response.defer(ephemeral=True)
        colors = build_colors_for_effect(
            self.state["effect_id"], self.state["primary_color"], self.state["secondary_color"]
        )
        result = await apply_display_style(
            self.cog.bot, self.guild_id,
            self.state["nickname"], self.state["font_id"], self.state["effect_id"],
            colors,
        )
        if result["success"]:
            self.state["updated_at"] = int(time.time())
            await self.cog.save_state(self.guild_id, self.state)
            f = get_font_by_id(self.state["font_id"])
            e = get_effect_by_id(self.state["effect_id"])
            await interaction.followup.send(
                view=_success_view(
                    f"**Style Applied!**\n\n"
                    f"**Name:** `{self.state['nickname']}`\n"
                    f"**Font:** `{f['name']}`\n"
                    f"**Effect:** `{e['name']}`\n"
                    f"**Colors:** `{dec_to_hex(self.state['primary_color'])}` → "
                    f"`{dec_to_hex(self.state['secondary_color'])}`"
                ),
                ephemeral=True,
            )
            await self._refresh(interaction)
        else:
            await interaction.followup.send(
                view=_error_view(f"**Apply Failed!**\n{format_error(result)}"),
                ephemeral=True,
            )

    async def _on_hex(self, interaction: discord.Interaction):
        if not await self._check(interaction): return
        await interaction.response.send_message(
            view=_info_view(
                "Send **two hex colors** separated by a space.\n"
                "Format: `#FF0000 #000000`\n"
                "*Timeout: 30 seconds*"
            ),
            ephemeral=True,
        )
        result = await self._wait_input(interaction, timeout=30.0)
        if not result:
            return await interaction.edit_original_response(view=_error_view("Timed out!"))
        parts = result.split()
        if len(parts) < 2:
            return await interaction.edit_original_response(
                view=_error_view("Send two hex colors!\nExample: `#FF0000 #000000`")
            )
        if not is_valid_hex(parts[0]) or not is_valid_hex(parts[1]):
            return await interaction.edit_original_response(
                view=_error_view("Invalid hex format! Use `#RRGGBB`")
            )
        self.state["primary_color"] = hex_to_dec(parts[0])
        self.state["secondary_color"] = hex_to_dec(parts[1])
        self.state["selected_preset"] = "Custom"
        await interaction.edit_original_response(
            view=_success_view(
                f"Colors set!\n`{dec_to_hex(self.state['primary_color'])}` → "
                f"`{dec_to_hex(self.state['secondary_color'])}`"
            )
        )
        await self._refresh(interaction)

    async def _on_edit(self, interaction: discord.Interaction):
        if not await self._check(interaction): return
        await interaction.response.send_message(
            view=_info_view(
                f"Send the new **nickname**.\n"
                f"Current: `{self.state['nickname']}`\n"
                f"*Timeout: 30 seconds*"
            ),
            ephemeral=True,
        )
        result = await self._wait_input(interaction, timeout=30.0)
        if not result:
            return await interaction.edit_original_response(view=_error_view("Timed out!"))
        if len(result) > 32:
            return await interaction.edit_original_response(
                view=_error_view("Nickname must be 32 characters or less.")
            )
        self.state["nickname"] = result
        await interaction.edit_original_response(view=_success_view(f"Nickname: `{result}`"))
        await self._refresh(interaction)

    async def _on_reset(self, interaction: discord.Interaction):
        if not await self._check(interaction): return
        await interaction.response.defer(ephemeral=True)
        try:
            await clear_display_style(self.cog.bot, self.guild_id)
            try:
                await interaction.guild.me.edit(nick=None)
            except Exception:
                pass
            self.state["nickname"] = interaction.guild.me.name
            self.state["font_id"] = 11
            self.state["effect_id"] = 1
            self.state["primary_color"] = 0xFFFFFF
            self.state["secondary_color"] = 0x000000
            self.state["selected_preset"] = "None"
            self.state["updated_at"] = int(time.time())
            await self.cog.delete_state(self.guild_id)
            await interaction.followup.send(
                view=_success_view("**Reset complete!** All styles cleared."),
                ephemeral=True,
            )
            await self._refresh(interaction)
        except Exception as e:
            await interaction.followup.send(
                view=_error_view(f"Reset failed: `{e}`"),
                ephemeral=True,
            )

    async def _on_close(self, interaction: discord.Interaction):
        if not await self._check(interaction): return
        try:
            await interaction.response.defer()
            await interaction.message.delete()
            self.stop()
        except Exception:
            pass

class Tag(commands.Cog):

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        DB_DIR.mkdir(exist_ok=True)
        FONT_DIR.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tag_style (
                    guild_id         INTEGER PRIMARY KEY,
                    nickname         TEXT,
                    font_id          INTEGER DEFAULT 11,
                    effect_id        INTEGER DEFAULT 1,
                    primary_color    INTEGER DEFAULT 16777215,
                    secondary_color  INTEGER DEFAULT 0,
                    selected_preset  TEXT DEFAULT 'None',
                    updated_at       INTEGER
                )
            """)
            await db.commit()

    async def load_state(self, guild_id: int) -> dict:
        async with aiosqlite.connect(str(DB_PATH)) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tag_style WHERE guild_id = ?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
        if not row:
            return {}
        return dict(row)

    async def save_state(self, guild_id: int, state: dict):
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute("""
                INSERT OR REPLACE INTO tag_style
                (guild_id, nickname, font_id, effect_id, primary_color,
                 secondary_color, selected_preset, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                guild_id,
                state.get("nickname"),
                state.get("font_id", 11),
                state.get("effect_id", 1),
                state.get("primary_color", 0xFFFFFF),
                state.get("secondary_color", 0x000000),
                state.get("selected_preset", "None"),
                state.get("updated_at", int(time.time())),
            ))
            await db.commit()

    async def delete_state(self, guild_id: int):
        async with aiosqlite.connect(str(DB_PATH)) as db:
            await db.execute("DELETE FROM tag_style WHERE guild_id = ?", (guild_id,))
            await db.commit()

    @commands.command(name="tag", aliases=["tags", "namestyle", "nameplate"])
    @commands.has_permissions(administrator=True)
    @commands.guild_only()
    async def tag(self, ctx: commands.Context):
        saved = await self.load_state(ctx.guild.id)
        state = {
            "nickname":        saved.get("nickname") or (ctx.guild.me.nick or ctx.guild.me.name),
            "font_id":         saved.get("font_id", 11),
            "effect_id":       saved.get("effect_id", 1),
            "primary_color":   saved.get("primary_color", 0xFFFFFF),
            "secondary_color": saved.get("secondary_color", 0x000000),
            "selected_preset": saved.get("selected_preset", "None"),
            "updated_at":      saved.get("updated_at"),
            "_author_id":      ctx.author.id,
        }

        view, file = build_main_view(self, ctx.guild.id, state)
        if file:
            await ctx.send(view=view, file=file)
        else:
            await ctx.send(view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Tag(bot))
