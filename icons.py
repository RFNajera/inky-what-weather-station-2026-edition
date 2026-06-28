"""
icons.py - Vector-style weather icons drawn with Pillow primitives.

No external image files are required. Each function draws an icon into a
bounding box (x, y, size) on a Pillow ImageDraw surface. Icons use only
three colours so they render crisply on a red/black/white Inky wHAT:
    BLACK  -> outlines / clouds / rain / snow
    RED    -> sun / lightning / "hot" accents
    WHITE  -> background / cut-outs

A single dispatcher, draw_icon(), maps a WMO weather code to the right glyph.
"""

from PIL import ImageDraw

# These palette indices match the Inky library:
#   0 = WHITE, 1 = BLACK, 2 = RED (or YELLOW on a yellow display)
WHITE = 0
BLACK = 1
ACCENT = 2  # red on your display


def _circle(draw, cx, cy, r, fill=None, outline=None, width=1):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=outline, width=width)


def _sun(draw, cx, cy, r, colour=ACCENT, rays=True):
    """A sun: filled disc with optional rays."""
    if rays:
        import math
        ray_inner = r + max(2, r // 3)
        ray_outer = r + max(5, int(r * 0.9))
        for i in range(8):
            ang = math.radians(i * 45)
            x1 = cx + ray_inner * math.cos(ang)
            y1 = cy + ray_inner * math.sin(ang)
            x2 = cx + ray_outer * math.cos(ang)
            y2 = cy + ray_outer * math.sin(ang)
            draw.line([x1, y1, x2, y2], fill=colour, width=max(2, r // 8))
    _circle(draw, cx, cy, r, fill=colour)


def _moon(draw, cx, cy, r, colour=BLACK):
    """A crescent moon (filled disc with a white disc cut out)."""
    _circle(draw, cx, cy, r, fill=colour)
    _circle(draw, cx + r // 2, cy - r // 3, r, fill=WHITE)


def _cloud(draw, cx, cy, w, colour=BLACK, fill=WHITE):
    """A puffy cloud centred horizontally at cx, baseline near cy.
    w is the overall cloud width."""
    h = int(w * 0.6)
    left = cx - w // 2
    top = cy - h // 2
    # base rounded rectangle
    draw.rounded_rectangle([left, cy - h // 4, left + w, cy + h // 4],
                           radius=h // 4, fill=fill, outline=colour, width=max(2, w // 30))
    # puffs
    r1 = int(h * 0.35)
    r2 = int(h * 0.45)
    r3 = int(h * 0.30)
    _circle(draw, left + int(w * 0.28), top + h // 3 + r1, r1, fill=fill, outline=colour, width=max(2, w // 30))
    _circle(draw, cx, top + r2, r2, fill=fill, outline=colour, width=max(2, w // 30))
    _circle(draw, left + int(w * 0.72), top + h // 3 + r3, r3, fill=fill, outline=colour, width=max(2, w // 30))
    # re-draw the base interior to cover overlapping outlines for a clean look
    draw.rectangle([left + 3, cy - h // 6, left + w - 3, cy + h // 5], fill=fill)


def _raindrops(draw, cx, cy, w, colour=BLACK, n=3):
    spacing = w // (n + 1)
    start = cx - w // 2 + spacing
    for i in range(n):
        x = start + i * spacing
        draw.line([x, cy, x - max(3, w // 18), cy + max(8, w // 6)], fill=colour, width=max(2, w // 35))


def _snowflakes(draw, cx, cy, w, colour=BLACK, n=3):
    spacing = w // (n + 1)
    start = cx - w // 2 + spacing
    s = max(4, w // 12)
    for i in range(n):
        x = start + i * spacing
        y = cy + max(6, w // 8)
        draw.line([x - s, y, x + s, y], fill=colour, width=2)
        draw.line([x, y - s, x, y + s], fill=colour, width=2)
        draw.line([x - s * 0.7, y - s * 0.7, x + s * 0.7, y + s * 0.7], fill=colour, width=2)
        draw.line([x - s * 0.7, y + s * 0.7, x + s * 0.7, y - s * 0.7], fill=colour, width=2)


def _bolt(draw, cx, cy, w, colour=ACCENT):
    s = w // 4
    pts = [
        (cx, cy - s),
        (cx - s // 2, cy + s // 4),
        (cx, cy + s // 4),
        (cx - s // 3, cy + s),
        (cx + s // 2, cy - s // 8),
        (cx, cy - s // 8),
    ]
    draw.polygon(pts, fill=colour)


def _fog(draw, cx, cy, w, colour=BLACK):
    h = max(3, w // 18)
    for i, frac in enumerate([0.9, 0.75, 0.9, 0.75]):
        y = cy - w // 4 + i * (w // 6)
        ww = int(w * frac)
        draw.line([cx - ww // 2, y, cx + ww // 2, y], fill=colour, width=h)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def draw_icon(draw, code, x, y, size, is_day=True):
    """Draw a weather icon for a WMO `code` into a square box at (x, y) of
    side `size`. `is_day` swaps sun<->moon for clear/partly-cloudy states."""
    cx = x + size // 2
    cy = y + size // 2

    # WMO weather interpretation codes
    # https://open-meteo.com/en/docs  (see weather_code table)
    if code in (0, 1):  # clear / mainly clear
        if is_day:
            _sun(draw, cx, cy, size // 4)
        else:
            _moon(draw, cx, cy, size // 4)
    elif code == 2:  # partly cloudy
        if is_day:
            _sun(draw, cx + size // 6, cy - size // 6, size // 6)
        else:
            _moon(draw, cx + size // 6, cy - size // 6, size // 7)
        _cloud(draw, cx - size // 12, cy + size // 8, int(size * 0.62))
    elif code == 3:  # overcast
        _cloud(draw, cx, cy, int(size * 0.72))
    elif code in (45, 48):  # fog
        _sun(draw, cx + size // 6, cy - size // 4, size // 8, rays=False) if is_day \
            else _moon(draw, cx + size // 6, cy - size // 4, size // 9)
        _fog(draw, cx, cy + size // 12, int(size * 0.78))
    elif code in (51, 53, 55, 56, 57):  # drizzle
        _cloud(draw, cx, cy - size // 8, int(size * 0.64))
        _raindrops(draw, cx, cy + size // 6, int(size * 0.55), n=2)
    elif code in (61, 63, 65, 66, 67, 80, 81, 82):  # rain / showers
        _cloud(draw, cx, cy - size // 8, int(size * 0.66))
        _raindrops(draw, cx, cy + size // 6, int(size * 0.6), n=3)
    elif code in (71, 73, 75, 77, 85, 86):  # snow
        _cloud(draw, cx, cy - size // 8, int(size * 0.66))
        _snowflakes(draw, cx, cy + size // 6, int(size * 0.6), n=3)
    elif code in (95, 96, 99):  # thunderstorm
        _cloud(draw, cx, cy - size // 8, int(size * 0.68))
        _bolt(draw, cx, cy + size // 6, int(size * 0.9))
    else:  # fallback -> cloud
        _cloud(draw, cx, cy, int(size * 0.7))
