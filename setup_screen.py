#!/usr/bin/env python3
"""
setup_screen.py - Wi-Fi "SETUP MODE" screen for the Inky wHAT.

When the station can't reach a known Wi-Fi network it falls back to a hotspot
(via Comitup) so you can add the new network from your phone. This module draws
a full-screen instruction card telling you exactly what to connect to and where
to go.

It is normally invoked by the Comitup state-change callback
(`comitup-callback`) with the hotspot name, but you can also render a preview:

    python3 setup_screen.py --preview
    python3 setup_screen.py --preview --ssid "WeatherStation-Setup"

The hotspot details (SSID and portal address) default to the values configured
in comitup.conf / this project's installer.
"""

import argparse
import os
import sys

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 400, 300

# Palette indices used by the Inky library (0=white, 1=black, 2=red)
WHITE = 0
BLACK = 1
RED = 2

# Defaults - keep these in sync with comitup.conf installed by install.sh
DEFAULT_SSID = "WeatherStation-Setup"
DEFAULT_PORTAL = "http://10.41.0.1"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PREVIEW_PATH = os.path.join(SCRIPT_DIR, "setup_preview.png")

# The hotspot password is stored ONLY on the device (never in the git repo).
# The installer generates a memorable phrase and writes it here; this screen
# reads it back so it can be shown on the display when you need to connect.
PASSWORD_FILE = os.path.join(SCRIPT_DIR, "wifi_password.txt")


def read_local_password():
    """Return the hotspot password from the local (git-ignored) file, or None
    if there isn't one (i.e. the hotspot is open)."""
    try:
        with open(PASSWORD_FILE, "r", encoding="utf-8") as fh:
            pw = fh.read().strip()
            return pw or None
    except OSError:
        return None


def load_fonts():
    reg = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    mono = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
    try:
        return {
            "title": ImageFont.truetype(bold, 30),
            "step": ImageFont.truetype(reg, 18),
            "step_b": ImageFont.truetype(bold, 18),
            "value": ImageFont.truetype(mono, 20),
            "small": ImageFont.truetype(reg, 14),
        }
    except OSError:
        d = ImageFont.load_default()
        return {k: d for k in ("title", "step", "step_b", "value", "small")}


def _text(draw, x, y, s, font, fill):
    draw.text((x, y), s, font=font, fill=fill)


def _centered(draw, cx, y, s, font, fill):
    b = draw.textbbox((0, 0), s, font=font)
    draw.text((cx - (b[2] - b[0]) / 2, y), s, font=font, fill=fill)


def render_setup(ssid=DEFAULT_SSID, portal=DEFAULT_PORTAL, password=None,
                 fonts=None):
    """Render the setup-mode instruction screen and return a Pillow image."""
    fonts = fonts or load_fonts()
    img = Image.new("P", (WIDTH, HEIGHT), WHITE)
    img.putpalette([255, 255, 255,  0, 0, 0,  255, 0, 0] + [0, 0, 0] * 253)
    draw = ImageDraw.Draw(img)

    # ---- Title bar (red) -------------------------------------------------
    title_h = 46
    draw.rectangle([0, 0, WIDTH, title_h], fill=RED)
    # a simple Wi-Fi glyph (three arcs + dot) on the left of the title
    gx, gy = 26, title_h // 2 + 6
    for i, r in enumerate((6, 13, 20)):
        draw.arc([gx - r, gy - r, gx + r, gy + r], start=225, end=315,
                 fill=WHITE, width=3)
    draw.ellipse([gx - 2, gy - 2, gx + 2, gy + 2], fill=WHITE)
    _centered(draw, WIDTH // 2 + 14, 8, "Wi-Fi SETUP MODE", fonts["title"], WHITE)

    # ---- Intro line ------------------------------------------------------
    y = title_h + 12
    _centered(draw, WIDTH // 2, y,
              "Can't reach a known network. Connect to set one up:",
              fonts["small"], BLACK)

    # ---- Step 1: join the hotspot ---------------------------------------
    y += 28
    _text(draw, 16, y, "1.", fonts["step_b"], BLACK)
    _text(draw, 40, y, "On your phone, join this Wi-Fi:", fonts["step"], BLACK)
    y += 24
    # Network name and (optional) password on their own labelled rows so both
    # stay easy to read on the e-ink panel.
    label_x, val_x = 40, 118
    _text(draw, label_x, y, "Network:", fonts["small"], BLACK)
    _text(draw, val_x, y - 3, ssid, fonts["value"], RED)
    y += 24
    if password:
        _text(draw, label_x, y, "Password:", fonts["small"], BLACK)
        _text(draw, val_x, y - 3, password, fonts["value"], RED)
        y += 24
    else:
        _text(draw, label_x, y, "(open network - no password)",
              fonts["small"], BLACK)
        y += 22

    # ---- Step 2: open the portal ----------------------------------------
    y += 6
    _text(draw, 16, y, "2.", fonts["step_b"], BLACK)
    _text(draw, 40, y, "A setup page opens. If not, visit:",
          fonts["step"], BLACK)
    y += 23
    _text(draw, 40, y, portal, fonts["value"], RED)

    # ---- Step 3: pick network -------------------------------------------
    y += 30
    _text(draw, 16, y, "3.", fonts["step_b"], BLACK)
    _text(draw, 40, y, "Pick the venue's Wi-Fi, enter its", fonts["step"], BLACK)
    y += 21
    _text(draw, 40, y, "password, and submit.", fonts["step"], BLACK)

    # ---- Footer ----------------------------------------------------------
    draw.line([12, HEIGHT - 26, WIDTH - 12, HEIGHT - 26], fill=BLACK, width=1)
    _centered(draw, WIDTH // 2, HEIGHT - 22,
              "The weather returns automatically once connected.",
              fonts["small"], BLACK)
    return img


def show_on_inky(img):
    from inky.auto import auto
    inky = auto(ask_user=False, verbose=False)
    img = img.resize((inky.width, inky.height))
    inky.set_image(img)
    inky.set_border(inky.WHITE)
    inky.show()


def main():
    ap = argparse.ArgumentParser(description="Render the Wi-Fi setup screen")
    ap.add_argument("--preview", action="store_true",
                    help="Save a PNG instead of writing to the display")
    ap.add_argument("--ssid", default=DEFAULT_SSID)
    ap.add_argument("--portal", default=DEFAULT_PORTAL)
    ap.add_argument("--password", default=None,
                    help="Hotspot password to show. If omitted, it's read "
                         "from the local wifi_password.txt (if present).")
    args = ap.parse_args()

    # If no password was passed explicitly, fall back to the local file.
    password = args.password if args.password is not None else read_local_password()

    img = render_setup(ssid=args.ssid, portal=args.portal,
                       password=password)
    img.save(PREVIEW_PATH)
    print(f"Saved preview -> {PREVIEW_PATH}")

    if not args.preview:
        try:
            show_on_inky(img)
            print("Displayed setup screen.")
        except Exception as e:
            print(f"ERROR updating display: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
