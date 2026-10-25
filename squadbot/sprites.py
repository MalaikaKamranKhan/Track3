"""Pixel-art characters built from the team mascot (assets/mascot.svg, a 24x24 pixel berry).

- hero(): the cute berry holding a sword (results screen)
- evil(mood, kind): its evil twin, a fruit-coloured berry with red eyes and fangs (battle cards).
  mood: angry | hurt | dead · kind: a fruit (grape, lime, lemon, tangerine, kiwi; fruit_for(topic) picks one)
  or lie (the dragonfruit liar)

Drop your own art in squadbot/assets/boss.png (or boss.svg in the same pixel-rect format as the mascot) and it's used
as the boss instead.
"""
from __future__ import annotations

import functools
import re
from pathlib import Path

ASSETS = Path(__file__).parent / "assets"
Px = dict[tuple[int, int], tuple[int, int, int]]


def _hex(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def load_svg(path: Path) -> tuple[int, int, Px]:
    """Read a pixel-art SVG made of <rect> cells. A rect covering the whole canvas is the background (left out)."""
    s = path.read_text()
    vb = re.search(r'viewBox="0 0 (\d+) (\d+)"', s)
    w, h = (int(vb.group(1)), int(vb.group(2))) if vb else (24, 24)
    px: Px = {}
    for attrs in re.findall(r"<rect\b([^>]*)/?>", s):
        get = dict(re.findall(r'(\w+)="([^"]*)"', attrs))
        x, y = int(float(get.get("x", 0))), int(float(get.get("y", 0)))
        rw, rh = int(float(get.get("width", 1))), int(float(get.get("height", 1)))
        fill = get.get("fill", "")
        if not fill.startswith("#") or (rw >= w and rh >= h):
            continue
        for i in range(x, x + rw):
            for j in range(y, y + rh):
                px[(i, j)] = _hex(fill)
    return w, h, px


@functools.lru_cache(maxsize=1)
def mascot() -> tuple[int, int, Px]:
    return load_svg(ASSETS / "mascot.svg")


# mascot palette
OUT, LIGHT, MAIN, SHADOW = _hex("2b211b"), _hex("3a8cef"), _hex("1f6fe0"), _hex("1b4fa8")
WHITE, LEAF, PINK = _hex("ffffff"), _hex("b8326e"), _hex("f3a6b8")

STEEL, STEEL_HI, GOLD, WOOD = (214, 222, 234), (248, 250, 255), (246, 196, 64), (139, 90, 43)


def _mirror(x: int) -> int:
    return 23 - x  # the berry is symmetric around x = 11.5


@functools.lru_cache(maxsize=1)
def hero() -> tuple[int, int, Px]:
    """The cute mascot, holding a sword up at its side."""
    _, h, base = mascot()
    px = dict(base)
    px[(21, 15)] = px[(22, 15)] = MAIN  # arm
    px[(22, 14)] = px[(22, 16)] = OUT
    px[(24, 1)] = OUT  # sword tip
    for y in range(2, 12):
        px[(23, y)], px[(24, y)], px[(25, y)] = OUT, STEEL_HI if y % 3 == 0 else STEEL, OUT
    for x in range(22, 27):
        px[(x, 12)] = GOLD
    px[(21, 12)] = px[(27, 12)] = OUT
    for y in range(13, 17):
        px[(23, y)], px[(24, y)], px[(25, y)] = OUT, WOOD, OUT
    px[(23, 15)] = LIGHT  # hand gripping the hilt
    for x in range(23, 26):
        px[(x, 17)] = GOLD
    return 28, h, px


PALETTES = {  # outline, light, main, shadow, shine, leaf, leaf highlight
    "grape": ((26, 14, 38), (146, 86, 214), (98, 44, 164), (60, 22, 112), (206, 172, 248), (34, 88, 52), (86, 156, 92)),
    "lime": ((18, 38, 14), (164, 218, 86), (112, 178, 48), (62, 122, 30), (222, 246, 172), (26, 84, 58), (60, 132, 88)),
    "lemon": ((58, 42, 8), (255, 232, 112), (240, 196, 40), (196, 142, 18), (255, 248, 204), (44, 112, 52), (92, 168, 88)),
    "tangerine": ((56, 22, 6), (255, 168, 76), (238, 120, 30), (184, 76, 14), (255, 214, 164), (44, 112, 52), (92, 168, 88)),
    "kiwi": ((36, 26, 12), (176, 138, 86), (128, 94, 52), (88, 62, 32), (214, 190, 142), (70, 138, 46), (130, 192, 76)),
    "lie": ((38, 12, 24), (232, 92, 150), (176, 40, 98), (112, 18, 60), (252, 182, 210), (60, 20, 34), (120, 40, 60)),
    "dead": ((40, 40, 48), (150, 152, 166), (112, 114, 130), (80, 82, 96), (190, 192, 204), (90, 92, 100), (130, 132, 140)),
}
FRUITS = ("grape", "lime", "lemon", "tangerine", "kiwi")  # topic bosses; "lie" is the dragonfruit liar


def fruit_for(topic: str) -> str:
    """The same topic always gets the same fruit boss."""
    return FRUITS[sum(topic.lower().encode()) % len(FRUITS)]
RED_EYE, GLINT, MOUTH, FANG, SWEAT, BANDAGE = (255, 64, 64), (255, 220, 96), (70, 8, 26), (252, 248, 236), (120, 200, 250), (246, 226, 196)
DARK_RED, BONE = (190, 30, 40), (236, 228, 208)


@functools.lru_cache(maxsize=12)
def evil(mood: str = "angry", kind: str = "boss") -> tuple[int, int, Px]:
    """The mascot's evil twin, recoloured, with an angry face, red eyes and fangs."""
    w, h, base = mascot()
    out, light, main, shadow, shine, leaf, leaf_hi = PALETTES["dead" if mood == "dead" else
                                                              "grape" if kind == "boss" else kind]
    swap = {OUT: out, LIGHT: light, MAIN: main, SHADOW: shadow, WHITE: shine, LEAF: leaf}
    px: Px = {}
    for (x, y), c in base.items():
        if y >= 20:  # drop the speech-bubble tail
            continue
        px[(x, y)] = leaf_hi if c == PINK and y < 6 else main if c == PINK else swap.get(c, c)
    for x in range(6, 18):  # close the bottom where the tail was
        px[(x, 20)] = out
    for y in range(8, 18):  # blank face
        for x in range(5, 20 if y > 8 else 18):
            if (x, y) in px:
                px[(x, y)] = main
    px[(5, 8)] = px[(6, 8)] = shine

    def both(x, y, c):
        px[(x, y)] = c
        px[(_mirror(x), y)] = c

    # horns
    for x, y, c in ((4, 5, out), (5, 5, BONE), (3, 4, out), (4, 4, BONE), (5, 4, out), (2, 3, out), (3, 3, BONE),
                    (4, 3, out), (3, 2, out)):
        both(x, y, c)

    if mood == "dead":
        for x, y in ((6, 11), (8, 11), (7, 12), (6, 13), (8, 13)):  # X eyes
            both(x, y, out)
        for x in range(9, 15):  # wobbly mouth
            px[(x, 16 if x % 2 else 15)] = out
        return w, h, px

    for x, y in ((5, 9), (6, 9), (7, 10), (8, 10)):  # angry brows slanting to the middle
        both(x, y, out)
    for x, y, c in ((6, 11, GLINT), (7, 11, RED_EYE), (8, 11, out),  # big glowing eyes
                    (6, 12, RED_EYE), (7, 12, RED_EYE), (8, 12, RED_EYE),
                    (6, 13, DARK_RED), (7, 13, RED_EYE), (8, 13, RED_EYE)):
        both(x, y, c)
    px[(7, 14)] = px[(16, 14)] = out  # grin with two fangs
    for x in range(8, 16):
        px[(x, 15)] = out
    px[(8, 16)], px[(15, 16)] = out, out
    for x in range(9, 15):
        px[(x, 16)] = FANG if x in (9, 14) else MOUTH
        px[(x, 17)] = out
    if mood == "hurt":
        for y in (11, 12, 13):  # one eye squeezed shut
            for x in (15, 16, 17):
                px[(x, y)] = out if y == 12 else main
        px[(1, 8)] = px[(1, 9)] = px[(0, 9)] = SWEAT
        for x, y in ((14, 7), (15, 7), (16, 7), (15, 6), (15, 8)):  # bandage
            px[(x, y)] = BANDAGE
    return w, h, px


def image(sprite: tuple[int, int, Px], scale: int):
    """The sprite as a transparent PIL image, `scale` screen pixels per cell."""
    from PIL import Image
    w, h, px = sprite
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    for (x, y), c in px.items():
        if 0 <= x < w and 0 <= y < h:
            img.putpixel((x, y), c + (255,))
    return img.resize((w * scale, h * scale), Image.NEAREST)


@functools.lru_cache(maxsize=1)
def custom_boss():
    """Your own boss art, if you added assets/boss.png or assets/boss.svg."""
    from PIL import Image
    if (ASSETS / "boss.png").exists():
        return Image.open(ASSETS / "boss.png").convert("RGBA")
    if (ASSETS / "boss.svg").exists():
        return image(load_svg(ASSETS / "boss.svg"), 1)
    return None


def boss_image(mood: str, kind: str, size: int):
    """The boss scaled to fit a size x size box."""
    from PIL import Image, ImageOps
    art = custom_boss()
    if art is None:
        sprite = evil(mood, kind)
        return image(sprite, max(1, size // max(sprite[0], sprite[1])))
    k = size / max(art.size)
    art = art.resize((max(1, round(art.width * k)), max(1, round(art.height * k))), Image.NEAREST)
    if mood == "dead":
        alpha = art.getchannel("A")
        art = ImageOps.grayscale(art).convert("RGBA")
        art.putalpha(alpha)
    return art
