"""Generate demo.gif from a scripted mini-dev transcript (no screen recording).

Run from the repo root:  python scripts/make_demo_gif.py
"""

import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

TRANSCRIPT = [
    '$ mindev run "create and edit a greeting file"',
    "",
    "Task: create and edit a greeting file",
    "[mode: readwrite]",
    "",
    "  -> write_file(path='greeting.txt', content='hello')",
    "  -> edit_file(path='greeting.txt', old_string='hello', new_string='hello world')",
    "  -> bash(command='echo hello')",
    "",
    "=" * 46,
    "Done: wrote greeting.txt, edited it, and ran a command.",
]

BG = (30, 30, 34)
FG = (225, 225, 225)
ACCENT = (122, 222, 152)
FONT_SIZE = 18
LINE_HEIGHT = 27
PAD = 18


def find_font():
    candidates = [
        "C:/Windows/Fonts/CascadiaMono.ttf",
        "C:/Windows/Fonts/cascadia.ttf",
        "C:/Windows/Fonts/consola.ttf",
        "C:/Windows/Fonts/DejaVuSansMono.ttf",
        "C:/Windows/Fonts/cour.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]
    for c in candidates:
        if os.path.exists(c):
            return ImageFont.truetype(c, FONT_SIZE)
    return ImageFont.load_default()


def color_for(index, line):
    if index == 0 or line.startswith("Done"):
        return ACCENT
    return FG


def main() -> int:
    font = find_font()
    probe = Image.new("RGB", (10, 10))
    d = ImageDraw.Draw(probe)
    width = int(max(d.textlength(line, font=font) for line in TRANSCRIPT)) + PAD * 2
    height = len(TRANSCRIPT) * LINE_HEIGHT + PAD * 2

    frames = []
    for i in range(1, len(TRANSCRIPT) + 1):
        img = Image.new("RGB", (width, height), BG)
        draw = ImageDraw.Draw(img)
        y = PAD
        for j, line in enumerate(TRANSCRIPT[:i]):
            draw.text((PAD, y), line, fill=color_for(j, line), font=font)
            y += LINE_HEIGHT
        frames.append(img)

    out = Path(__file__).resolve().parent.parent / "demo.gif"
    frames[0].save(
        out, save_all=True, append_images=frames[1:], duration=500, loop=0
    )
    print(f"wrote {out} ({width}x{height}, {len(frames)} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
