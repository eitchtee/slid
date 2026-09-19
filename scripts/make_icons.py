"""Draws Slid's icons: a 3x3 sliding board whose middle row is solved, with one gap.

Run with: uv run --with pillow python scripts/make_icons.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).parent.parent / "slid" / "static"
BG, TILE, WORD = "#2a2622", "#f4efe6", "#4f8a5b"
GAP_CELL = (2, 2)  # bottom-right
# Everything in a 32-unit box, like the SVG.
PAD, CELL, STEP, RADIUS = 5.9, 6.2, 7.0, 1.4


def tiles():
    for r in range(3):
        for c in range(3):
            if (r, c) != GAP_CELL:
                yield PAD + c * STEP, PAD + r * STEP, WORD if r == 1 else TILE


def svg() -> str:
    rects = "\n".join(
        f'  <rect x="{x:g}" y="{y:g}" width="{CELL}" height="{CELL}" rx="{RADIUS}" fill="{fill}"/>'
        for x, y, fill in tiles()
    )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">\n'
        "  <!-- A 3x3 sliding board: the middle row spells the word, bottom-right is the gap -->\n"
        f'  <rect width="32" height="32" rx="7" fill="{BG}"/>\n{rects}\n</svg>\n'
    )


def png(size: int, rounded: bool, inset: float = 1.0) -> Image.Image:
    """``inset`` shrinks the tiles toward the centre (maskable icons keep them in the safe zone)."""
    scale = size / 32
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # iOS and Android round these icons themselves, so only the favicons get corners.
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=7 * scale if rounded else 0, fill=BG)
    s = scale * inset
    offset = size * (1 - inset) / 2
    for x, y, fill in tiles():
        box = (offset + x * s, offset + y * s, offset + (x + CELL) * s, offset + (y + CELL) * s)
        d.rounded_rectangle(box, radius=RADIUS * s, fill=fill)
    return img


(OUT / "icons").mkdir(exist_ok=True)
(OUT / "icons" / "icon.svg").write_text(svg())
png(180, rounded=False).save(OUT / "icons" / "apple-touch-icon.png")
png(192, rounded=True).save(OUT / "icons" / "icon-192.png")
png(512, rounded=True).save(OUT / "icons" / "icon-512.png")
png(512, rounded=False, inset=0.75).save(OUT / "icons" / "icon-maskable-512.png")
png(256, rounded=True).save(OUT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
