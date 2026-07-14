#!/usr/bin/env python3
"""
weather.py - Inky wHAT weather station

Fetches current conditions + a 5-day forecast from Open-Meteo (no API key
needed) and renders them to a Pimoroni Inky wHAT (400x300, red/black/white).

Active weather watches & warnings for the location come from the US National
Weather Service (api.weather.gov, also free / no key) and appear as a red
banner across the bottom of the left panel when one is in effect.

Layout
------
+--------------------------------------------------+
|  LAST UPDATED ............ (top strip)           |
+----------------------------+---------------------+
|  [icon]  BIG TEMP  F       |  Mon  [icon]  88/68 |
|          (H 88\u00b0  L 68\u00b0)      |  Tue  [icon]  90/65 |
|         Description        |  Wed  [icon]  92/68 |
|   Feels like  ..           |  Thu  [icon]  96/68 |
|   Humidity    ..           |  Fri  [icon]  98/75 |
|   Wind        ..           |                     |
| [!! RED ALERT BANNER !!]   |                     |
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

# A contact e-mail is required by the NWS API's User-Agent policy.
NWS_CONTACT = "rfnajera@gmail.com"

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
            "huge": ImageFont.truetype(bold, 66),      # big current temp
            "big": ImageFont.truetype(bold, 26),       # condition label / unit
            "med": ImageFont.truetype(regular, 18),    # detail rows
            "hilo": ImageFont.truetype(bold, 16),      # today's hi/lo pill
            "small": ImageFont.truetype(regular, 16),
            "tiny": ImageFont.truetype(regular, 13),
            "day_bold": ImageFont.truetype(bold, 15),
        }
    except OSError:
        d = ImageFont.load_default()
        return {k: d for k in ("huge", "big", "med", "hilo", "small", "tiny",
                               "day_bold")}


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


def fetch_alerts():
    """Return a list of active NWS watch/warning event names for our location,
    most severe first, de-duplicated. Returns [] on any error so a network
    hiccup never blanks the weather display.

    We only surface WATCHES and WARNINGS (per the project spec); advisories,
    statements, and test messages are filtered out.
    """
    url = (
        "https://api.weather.gov/alerts/active"
        f"?point={LATITUDE},{LONGITUDE}"
    )
    headers = {
        # NWS asks for an identifying User-Agent with a contact address.
        "User-Agent": f"inky-weather/1.0 ({NWS_CONTACT})",
        "Accept": "application/geo+json",
    }
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"WARNING fetching alerts: {e}", file=sys.stderr)
        return []

    # Rank by severity so the worst alert wins the (single) banner line.
    sev_rank = {"Extreme": 0, "Severe": 1, "Moderate": 2, "Minor": 3,
                "Unknown": 4}
    events = []
    for f in data.get("features", []):
        p = f.get("properties", {})
        event = (p.get("event") or "").strip()
        if not event:
            continue
        # Keep only watches & warnings; drop advisories/statements/tests.
        low = event.lower()
        if "warning" not in low and "watch" not in low:
            continue
        events.append((sev_rank.get(p.get("severity"), 4), event))

    # De-duplicate event names while keeping the most-severe ordering.
    events.sort(key=lambda t: t[0])
    seen, ordered = set(), []
    for _, event in events:
        if event not in seen:
            seen.add(event)
            ordered.append(event)
    return ordered


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


def _fit_text(draw, text, font, max_w):
    """Truncate `text` with an ellipsis so it fits within max_w pixels."""
    if draw.textlength(text, font=font) <= max_w:
        return text
    ell = "\u2026"
    while text and draw.textlength(text + ell, font=font) > max_w:
        text = text[:-1]
    return text.rstrip() + ell


def _draw_alert_banner(draw, alerts, fonts, x, y, w, h):
    """Draw a red-background alert banner. `alerts` is a list of NWS event
    names (already most-severe-first). Shows a warning triangle, then the
    most severe alert; if more are active, appends a "+N more" hint."""
    pad = 6
    tri_w = 22
    # Warning triangle (white on the red bar) with an exclamation mark.
    cx = x + pad + tri_w // 2
    cy = y + h // 2
    r = tri_w // 2
    draw.polygon([(cx, cy - r), (cx - r, cy + r), (cx + r, cy + r)],
                 fill=WHITE)
    draw.line([cx, cy - r // 2, cx, cy + r // 4], fill=RED, width=3)
    draw.ellipse([cx - 1, cy + r // 2 - 1, cx + 1, cy + r // 2 + 1],
                 fill=RED)

    text_x = x + pad + tri_w + 6
    text_w = (x + w) - text_x - pad

    extra = len(alerts) - 1
    suffix = f"  +{extra} MORE" if extra > 0 else ""

    # Offer progressively shorter renderings of the primary event so a long
    # name like "Severe Thunderstorm Warning" stays readable instead of being
    # cut to "...WARN\u2026". WATCH is kept verbatim (shorter word).
    full = alerts[0].upper()
    abbreviated = (full
                   .replace("WARNING", "WARN")
                   .replace("THUNDERSTORM", "T-STORM")
                   .replace("ADVISORY", "ADV"))
    candidates = [full, abbreviated]

    # Try each candidate at each font size; take the first that fits.
    for cand in candidates:
        for font_key in ("day_bold", "small", "tiny"):
            f = fonts[font_key]
            suffix_w = draw.textlength(suffix, font=f) if suffix else 0
            if draw.textlength(cand, font=f) + suffix_w <= text_w:
                th = draw.textbbox((0, 0), cand, font=f)[3]
                ty = y + (h - th) // 2 - 2
                draw.text((text_x, ty), cand, font=f, fill=WHITE)
                if suffix:
                    draw.text((text_x + draw.textlength(cand, font=f), ty),
                              suffix, font=f, fill=WHITE)
                return
    # Last resort: truncate the abbreviated event to fit the smallest font.
    f = fonts["tiny"]
    fitted = _fit_text(draw, abbreviated + suffix, f, text_w)
    th = draw.textbbox((0, 0), fitted, font=f)[3]
    draw.text((text_x, y + (h - th) // 2 - 2), fitted, font=f, fill=WHITE)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
def render(data, fonts, alerts=None):
    alerts = alerts or []
    img = Image.new("P", (WIDTH, HEIGHT), WHITE)
    # Tell Pillow which RGB the 3 palette slots map to (for the PNG preview)
    img.putpalette([255, 255, 255,   0, 0, 0,   255, 0, 0] + [0, 0, 0] * 253)
    draw = ImageDraw.Draw(img)

    cur = data["current"]
    daily = data["daily"]

    # Reserve space at the bottom of the LEFT panel for an alert banner, but
    # only when there's actually an alert to show.
    banner_h = 40 if alerts else 0

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

    # Today's forecast high/low (index 0 = today) shown next to the current
    # temperature so you can see at a glance how much more the day still has
    # to give.
    today_hi = round(daily["temperature_2m_max"][0])
    today_lo = round(daily["temperature_2m_min"][0])

    # big current icon, top-left of the window
    icon_size = 88
    icons.draw_icon(draw, code, 14, strip_h + 6, icon_size, is_day=is_day)

    # big temperature to the right of the icon
    temp_str = f"{temp}\u00b0"
    temp_x = 108
    draw.text((temp_x, strip_h + 4), temp_str, font=fonts["huge"], fill=BLACK)
    temp_w = draw.textlength(temp_str, font=fonts["huge"])
    # small unit letter, tucked just under the degree symbol so it never
    # collides with the column divider
    unit_x = min(temp_x + temp_w - 2, split_x - 20)
    draw.text((unit_x, strip_h + 50), TEMP_SYMBOL, font=fonts["big"], fill=RED)

    # Today's Hi / Lo, just below the big temperature.
    hilo_str = f"H {today_hi}\u00b0   L {today_lo}\u00b0"
    hilo_w = draw.textlength(hilo_str, font=fonts["hilo"])
    # keep the pill aligned under the big temperature block
    hilo_x = temp_x
    hilo_y = strip_h + 78
    # subtle red outline pill so it reads as a distinct today-summary chip
    draw.rounded_rectangle(
        [hilo_x - 4, hilo_y - 2, hilo_x + hilo_w + 6, hilo_y + 20],
        radius=8, outline=RED, width=1)
    draw.text((hilo_x, hilo_y), hilo_str, font=fonts["hilo"], fill=RED)

    # condition description, centred under the icon/temp/hi-lo block
    desc = wmo_text(code)
    text_centered(draw, left_cx, strip_h + 108, desc, fonts["big"], BLACK)

    # detail rows (nudge up slightly when a banner is present so nothing
    # collides with it)
    detail_y = strip_h + 144 - (12 if banner_h else 0)
    line_gap = 22
    details = [
        f"Feels like  {feels}\u00b0{TEMP_SYMBOL}",
        f"Humidity   {humidity}%",
        f"Wind       {wind} {WIND_UNIT} {wdir}",
    ]
    for i, line in enumerate(details):
        draw.text((20, detail_y + i * line_gap), line, font=fonts["med"], fill=BLACK)

    # ---- Alert banner across the bottom of the LEFT panel ----------------
    if banner_h:
        by0 = HEIGHT - banner_h
        # solid red bar spanning the left column only (up to the divider)
        draw.rectangle([0, by0, split_x, HEIGHT], fill=RED)
        _draw_alert_banner(draw, alerts, fonts, 0, by0, split_x, banner_h)

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
    ap.add_argument("--demo-alert", metavar="EVENT", nargs="?",
                    const="Severe Thunderstorm Warning",
                    help="Force a sample alert banner (for previews/testing). "
                         "Optionally pass an event name.")
    args = ap.parse_args()

    fonts = load_fonts()
    try:
        data = fetch_weather()
    except Exception as e:
        print(f"ERROR fetching weather: {e}", file=sys.stderr)
        sys.exit(1)

    if args.demo_alert:
        alerts = [args.demo_alert]
    elif args.demo_alert is not None:
        # --demo-alert "" explicitly requests a no-alert render.
        alerts = []
    else:
        # Alerts are best-effort: a failure here returns [] and the display
        # still shows the weather.
        alerts = fetch_alerts()
    if alerts:
        print(f"Active watches/warnings: {alerts}")

    img = render(data, fonts, alerts=alerts)
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
