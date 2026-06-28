#!/usr/bin/env python3
"""
weather.py - Inky wHAT weather station

Fetches current conditions + a 5-day forecast from Open-Meteo (no API key
needed) and renders them to a Pimoroni Inky wHAT (400x300, red/black/white).

Layout
------
+--------------------------------------------------+
|  LAST UPDATED ............ (top strip)           |
+----------------------------+---------------------+
|                            |  Mon  [icon]  88/68 |
|   CURRENT WEATHER          |  Tue  [icon]  90/65 |
|   (left 2/3 "window")      |  Wed  [icon]  92/68 |
|   big temp, icon, desc,    |  Thu  [icon]  96/68 |
|   feels-like, humidity,    |  Fri  [icon]  98/75 |
|   wind                     |                     |
+----------------------------+---------------------+

Run with --preview to render to weather_preview.png on a machine without the
hardware (used during development). On the Pi it talks to the real display.
"""

import argparse
import datetime as dt
import json
import os
import sys
import urllib.request

from PIL import Image, ImageDraw, ImageFont

import icons

# ---------------------------------------------------------------------------
# Configuration  (edit these for a different location / units)
# ---------------------------------------------------------------------------
LATITUDE = 39.3881          # Mount Airy, MD  (ZIP 21771)
LONGITUDE = -77.1723
LOCATION_NAME = "Mount Airy, MD"
TIMEZONE = "America/New_York"
TEMP_UNIT = "fahrenheit"    # "fahrenheit" or "celsius"
WIND_UNIT = "mph"           # "mph", "kmh", "ms", "kn"
TEMP_SYMBOL = "F" if TEMP_UNIT == "fahrenheit" else "C"

WIDTH, HEIGHT = 400, 300

# Palette indices used by the Inky library
WHITE = 0
BLACK = 1
RED = 2

# Where to write the on-disk preview / debug copy of each render
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PREVIEW_PATH = os.path.join(SCRIPT_DIR, "weather_preview.png")

# ---------------------------------------------------------------------------
# WMO weather code -> short human text
# https://open-meteo.com/en/docs
# ---------------------------------------------------------------------------
WMO_TEXT = {
    0: "Clear", 1: "Mainly Clear", 2: "Partly Cloudy", 3: "Overcast",
    45: "Fog", 48: "Rime Fog",
    51: "Light Drizzle", 53: "Drizzle", 55: "Dense Drizzle",
    56: "Freezing Drizzle", 57: "Freezing Drizzle",
    61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
    66: "Freezing Rain", 67: "Freezing Rain",
    71: "Light Snow", 73: "Snow", 75: "Heavy Snow", 77: "Snow Grains",
    80: "Light Showers", 81: "Showers", 82: "Heavy Showers",
    85: "Snow Showers", 86: "Snow Showers",
    95: "Thunderstorm", 96: "Thunderstorm", 99: "Thunderstorm",
}


def wmo_text(code):
    return WMO_TEXT.get(code, "Unknown")


# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
def load_fonts():
    """Try to use DejaVu (ships with Debian's fonts-dejavu). Fall back to
    Pillow's default bitmap font if unavailable."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    regular = candidates[0]
    bold = candidates[1]
    try:
        return {
            "huge": ImageFont.truetype(bold, 76),
            "big": ImageFont.truetype(bold, 30),
            "med": ImageFont.truetype(regular, 20),
            "small": ImageFont.truetype(regular, 16),
            "tiny": ImageFont.truetype(regular, 13),
            "day_bold": ImageFont.truetype(bold, 15),
        }
    except OSError:
        d = ImageFont.load_default()
        return {k: d for k in ("huge", "big", "med", "small", "tiny", "day_bold")}


# ---------------------------------------------------------------------------
# Data fetch
# ---------------------------------------------------------------------------
def fetch_weather():
    url = (
        "https://api.open-meteo.com/v1/forecast"
        f"?latitude={LATITUDE}&longitude={LONGITUDE}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        "is_day,weather_code,wind_speed_10m,wind_direction_10m"
        "&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        "precipitation_probability_max"
        f"&temperature_unit={TEMP_UNIT}&wind_speed_unit={WIND_UNIT}"
        f"&timezone={TIMEZONE.replace('/', '%2F')}&forecast_days=6"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "inky-weather/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def text_centered(draw, cx, y, text, font, fill):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    draw.text((cx - w / 2, y), text, font=font, fill=fill)
    return bbox[3] - bbox[1]


def compass(deg):
    dirs = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    return dirs[int((deg + 22.5) % 360 // 45)]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render(data, fonts):
    img = Image.new("P", (WIDTH, HEIGHT), WHITE)
    # Tell Pillow which RGB the 3 palette slots map to (for the PNG preview)
    img.putpalette([255, 255, 255,   0, 0, 0,   255, 0, 0] + [0, 0, 0] * 253)
    draw = ImageDraw.Draw(img)

    cur = data["current"]
    daily = data["daily"]

    # ---- Top strip: last updated -----------------------------------------
    now = dt.datetime.now()
    updated = now.strftime("%a %b %-d, %-I:%M %p")
    strip_h = 22
    draw.rectangle([0, 0, WIDTH, strip_h], fill=BLACK)
    draw.text((6, 4), LOCATION_NAME, font=fonts["small"], fill=WHITE)
    upd_text = f"Updated {updated}"
    bbox = draw.textbbox((0, 0), upd_text, font=fonts["tiny"])
    draw.text((WIDTH - (bbox[2] - bbox[0]) - 6, 6), upd_text, font=fonts["tiny"], fill=WHITE)

    # ---- Column divider ---------------------------------------------------
    split_x = int(WIDTH * 2 / 3)  # ~266
    draw.line([split_x, strip_h, split_x, HEIGHT], fill=BLACK, width=2)

    # ---- LEFT 2/3: current weather "window" ------------------------------
    code = cur["weather_code"]
    is_day = bool(cur.get("is_day", 1))
    temp = round(cur["temperature_2m"])
    feels = round(cur["apparent_temperature"])
    humidity = cur["relative_humidity_2m"]
    wind = round(cur["wind_speed_10m"])
    wdir = compass(cur["wind_direction_10m"])

    left_cx = split_x // 2

    # big current icon, top-left of the window
    icon_size = 96
    icons.draw_icon(draw, code, 14, strip_h + 10, icon_size, is_day=is_day)

    # big temperature to the right of the icon
    temp_str = f"{temp}\u00b0"
    temp_x = 116
    draw.text((temp_x, strip_h + 6), temp_str, font=fonts["huge"], fill=BLACK)
    # small unit letter, tucked just under the degree symbol so it never
    # collides with the column divider
    unit_x = temp_x + draw.textlength(temp_str, font=fonts["huge"]) - 2
    # keep the unit letter safely inside the left column
    unit_x = min(unit_x, split_x - 22)
    draw.text((unit_x, strip_h + 60), TEMP_SYMBOL, font=fonts["big"], fill=RED)

    # condition description, centred under the icon/temp block
    desc = wmo_text(code)
    text_centered(draw, left_cx, strip_h + 116, desc, fonts["big"], BLACK)

    # detail rows
    detail_y = strip_h + 158
    line_gap = 26
    details = [
        f"Feels like  {feels}\u00b0{TEMP_SYMBOL}",
        f"Humidity   {humidity}%",
        f"Wind       {wind} {WIND_UNIT} {wdir}",
    ]
    for i, line in enumerate(details):
        draw.text((20, detail_y + i * line_gap), line, font=fonts["med"], fill=BLACK)

    # ---- RIGHT 1/3: 5-day forecast ---------------------------------------
    right_x = split_x
    right_w = WIDTH - split_x
    rcx = right_x + right_w // 2

    text_centered(draw, rcx, strip_h + 4, "5-DAY", fonts["day_bold"], RED)

    # 5 forecast rows, days index 1..5 (skip today at index 0)
    rows_top = strip_h + 24
    rows_bottom = HEIGHT - 4
    n = 5
    row_h = (rows_bottom - rows_top) // n

    for i in range(n):
        d_idx = i + 1
        date = dt.date.fromisoformat(daily["time"][d_idx])
        dcode = daily["weather_code"][d_idx]
        hi = round(daily["temperature_2m_max"][d_idx])
        lo = round(daily["temperature_2m_min"][d_idx])

        ry = rows_top + i * row_h
        # subtle separator
        if i > 0:
            draw.line([right_x + 8, ry, WIDTH - 8, ry], fill=BLACK, width=1)

        # day-of-week label (top-left of the row)
        day_lbl = date.strftime("%a")
        draw.text((right_x + 7, ry + 4), day_lbl,
                  font=fonts["day_bold"], fill=BLACK)

        # hi / lo stacked at the row's right edge
        hi_str = f"{hi}\u00b0"
        lo_str = f"{lo}\u00b0"
        draw.text((WIDTH - 38, ry + 3), hi_str, font=fonts["small"], fill=BLACK)
        draw.text((WIDTH - 38, ry + 21), lo_str, font=fonts["tiny"], fill=RED)

        # small icon centred in the lower part of the row
        isz = min(row_h - 6, 32)
        icons.draw_icon(draw, dcode, right_x + 10,
                        ry + row_h - isz - 1, isz, is_day=True)

    return img


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
def show_on_inky(img):
    from inky.auto import auto
    inky = auto(ask_user=False, verbose=False)
    img = img.resize((inky.width, inky.height))
    inky.set_image(img)
    inky.set_border(inky.WHITE)
    inky.show()


def main():
    ap = argparse.ArgumentParser(description="Inky wHAT weather station")
    ap.add_argument("--preview", action="store_true",
                    help="Render to a PNG instead of the display")
    args = ap.parse_args()

    fonts = load_fonts()
    try:
        data = fetch_weather()
    except Exception as e:
        print(f"ERROR fetching weather: {e}", file=sys.stderr)
        sys.exit(1)

    img = render(data, fonts)
    img.save(PREVIEW_PATH)
    print(f"Saved preview -> {PREVIEW_PATH}")

    if not args.preview:
        try:
            show_on_inky(img)
            print("Updated Inky wHAT display.")
        except Exception as e:
            print(f"ERROR updating display: {e}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
