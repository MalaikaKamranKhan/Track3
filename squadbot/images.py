"""Picture cards for Discord: the boss, the results podium and player profiles.

Drawn with Pillow from the game state (no AI, no network), so they're instant and free. Any error returns None and
the message goes out as a normal text card instead. Turn them off with IMAGES=off in .env.
"""
from __future__ import annotations

import functools
import hashlib
import io
import logging
import re
from pathlib import Path

from . import config, progress, sprites

log = logging.getLogger("squad.images")

FONTS = Path(__file__).parent / "assets" / "fonts"
BOLD, REG, PIX = "Outfit-Bold.ttf", "Outfit-Regular.ttf", "PixelifySans-Medium.ttf"
S = 2  # draw at 2x, then shrink, for smooth edges

BG, PANEL, TRACK = (22, 23, 36), (36, 38, 58), (48, 50, 74)
TEXT, MUTED = (241, 242, 248), (150, 154, 180)
RED, GREEN, GOLD = (236, 76, 88), (46, 200, 142), (246, 186, 52)
MEDALS = [(246, 196, 64), (196, 202, 216), (214, 136, 72)]
PALETTE = [(222, 96, 56), (132, 118, 236), (58, 146, 232), (222, 88, 138), (34, 170, 124), (240, 150, 40)]


def safe(fn):
    """Images are a bonus: never let one break a battle."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        if not config.IMAGES:
            return None
        try:
            return fn(*args, **kwargs)
        except Exception:  # noqa: BLE001
            log.exception("couldn't draw %s image", fn.__name__)
            return None
    return wrapper


@functools.lru_cache(maxsize=None)
def font(name: str, size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype(str(FONTS / name), size * S)
    except OSError:
        return ImageFont.load_default(size * S)


def clean(text, limit: int = 40) -> str:
    """Drop emoji and symbols the fonts can't draw, and shorten."""
    s = "".join(ch for ch in str(text) if ord(ch) < 0x2000 or 0x2010 <= ord(ch) <= 0x2027)
    s = re.sub(r"\s+", " ", s).strip()
    return s if len(s) <= limit else s[: limit - 3].rstrip() + "..."


def color_for(key: str) -> tuple[int, int, int]:
    return PALETTE[int(hashlib.md5(key.lower().encode()).hexdigest(), 16) % len(PALETTE)]


def tint(c, k: float):
    return tuple(max(0, min(255, int(v * k))) for v in c)


class Canvas:
    def __init__(self, w: int, h: int):
        from PIL import Image, ImageDraw
        self.w, self.h = w, h
        self.img = Image.new("RGBA", (w * S, h * S), BG + (255,))
        self.d = ImageDraw.Draw(self.img)

    def p(self, x, y):
        return (x * S, y * S)

    def glow(self, cx, cy, r, color, alpha=110):
        """A soft coloured light behind something (blurred small, then scaled up: fast)."""
        from PIL import Image, ImageDraw, ImageFilter
        k = 8
        layer = Image.new("RGBA", (self.w * S // k, self.h * S // k), (0, 0, 0, 0))
        ImageDraw.Draw(layer).ellipse([(cx - r) * S / k, (cy - r) * S / k, (cx + r) * S / k, (cy + r) * S / k],
                                      fill=color + (alpha,))
        layer = layer.filter(ImageFilter.GaussianBlur(r * S / k / 2.5)).resize(self.img.size, Image.BILINEAR)
        self.img.alpha_composite(layer)

    def rect(self, x, y, w, h, fill, r=0):
        if w <= 0 or h <= 0:
            return
        self.d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], min(r, w / 2, h / 2) * S, fill=fill)

    def text(self, x, y, s, f, fill=TEXT, anchor="la"):
        self.d.text((x * S, y * S), s, font=f, fill=fill, anchor=anchor)

    def width(self, s, f) -> float:
        return self.d.textlength(s, font=f) / S

    def wrap(self, s, f, width, lines=2) -> list[str]:
        out, cur = [], ""
        for word in s.split():
            trial = f"{cur} {word}".strip()
            if not cur or self.width(trial, f) <= width:
                cur = trial
            else:
                out.append(cur)
                cur = word
        if cur:
            out.append(cur)
        if len(out) > lines:
            out = out[:lines]
            out[-1] = out[-1].rstrip(".,") + "..."
        return out

    def bar(self, x, y, w, pct, color, label):
        pct = max(0.0, min(100.0, pct))
        self.text(x, y, label, font(PIX, 19), MUTED)
        self.text(x + w, y - 4, f"{round(pct)}%", font(BOLD, 24), TEXT, "ra")
        by, h = y + 30, 26
        self.rect(x, by, w, h, TRACK, 13)
        if pct > 0:
            self.rect(x, by, max(h, w * pct / 100), h, color, 13)
            self.rect(x + 8, by + 5, max(0, w * pct / 100 - 16), 5, tint(color, 1.25), 3)  # shine
        for i in range(1, 10):  # segment ticks, like a game HP bar
            self.d.line([self.p(x + w * i / 10, by + 4), self.p(x + w * i / 10, by + h - 4)], fill=BG, width=2 * S)

    def pill(self, x, y, s, f, fill, ink=BG, anchor="left"):
        tw = self.width(s, f)
        w, h = tw + 28, f.size / S + 16
        x0 = x - w if anchor == "right" else x - w / 2 if anchor == "center" else x
        self.rect(x0, y, w, h, fill, h / 2)
        self.text(x0 + w / 2, y + h / 2, s, f, ink, "mm")
        return w

    def sprite(self, img, x, y):
        """Paste a pixel sprite (PIL image at 1x) with its top-left at (x, y), keeping the pixels crisp."""
        from PIL import Image
        big = img.resize((img.width * S, img.height * S), Image.NEAREST)
        self.img.alpha_composite(big, (int(x * S), int(y * S)))

    def png(self) -> bytes:
        from PIL import Image
        out = self.img.resize((self.w, self.h), Image.LANCZOS).convert("RGB")
        buf = io.BytesIO()
        out.save(buf, "PNG", optimize=True)
        return buf.getvalue()


# the three picture cards ----------------------------------------------------------------

@safe
def battle(game, name: str, stamp: str = "", stamp_color=GOLD) -> bytes:
    """The boss with both HP bars. `stamp` is a hit marker for reveals, e.g. "CRIT!" or "-34 HP"."""
    c = Canvas(960, 380)
    kind = "lie" if game.mode == "lie" else "boss"
    color = (232, 92, 150) if kind == "lie" else (146, 86, 214)
    mood = "dead" if game.hp <= 0 else "hurt" if game.hp < 40 else "angry"
    c.glow(200, 190, 210, color if mood != "dead" else (90, 90, 110))
    art = sprites.boss_image(mood, kind, 264)
    c.sprite(art, 200 - art.width / 2, 190 - art.height / 2)
    x, w = 410, 510
    tag = "TWO TRUTHS & A LIE" if game.mode == "lie" else "BOSS BATTLE"
    if game.course:
        tag += f"  /  {clean(game.course, 18).upper()}"
    c.text(x, 46, tag, font(PIX, 22), tint(color, 1.3))
    title = font(BOLD, 44 if len(name) < 26 else 38)
    y = 80
    for line in c.wrap(clean(name, 60), title, w):
        c.text(x, y, line, title)
        y += title.size / S + 4
    total = len(game.questions)
    q = min(game.current + 1, total)
    c.text(x, y + 6, f"{clean(game.topic, 44)}  ·  question {q} of {total}", font(REG, 21), MUTED)
    c.bar(x, 226, w, game.hp, RED, "BOSS HP")
    c.bar(x, 298, w, game.squad_hp, GREEN, "SQUAD HP")
    if stamp:
        c.pill(940, 30, stamp, font(PIX, 30), stamp_color, anchor="right")
    if mood == "dead":
        c.pill(200, 330, "DEFEATED", font(PIX, 26), GREEN, anchor="center")
    return c.png()


@safe
def results(game, name: str, board: list[tuple[str, str, int]], weak: list[str]) -> bytes:
    """Outcome banner plus a podium for the top 3."""
    c = Canvas(960, 450)
    head, col = {"victory": ("VICTORY!", GREEN), "wiped": ("SQUAD WIPED", RED)}.get(game.outcome, ("BOSS SURVIVED", GOLD))
    c.glow(480, 70, 260, col, 90)
    c.text(480, 30, head, font(PIX, 60), col, "ma")
    sub = f"{clean(name, 40)} defeated" if game.outcome == "victory" else f"{clean(name, 40)} kept {round(game.hp)}% HP"
    c.text(480, 104, sub, font(REG, 24), MUTED, "ma")
    base = 392
    spots = [(480, 172), (300, 134), (660, 106)]  # (x, block height) for 1st, 2nd, 3rd
    if not board:
        c.text(480, 270, "No one played this round", font(BOLD, 30), MUTED, "mm")
    for rank, (uid, pname, pts) in enumerate(board[:3]):
        x, h = spots[rank]
        top = base - h
        c.rect(x - 80, top, 160, h, PANEL, 12)
        c.rect(x - 66, top, 132, 6, MEDALS[rank], 3)
        r = 26
        c.d.ellipse([c.p(x - r, top - r), c.p(x + r, top + r)], fill=MEDALS[rank])
        c.text(x, top, str(rank + 1), font(BOLD, 28), BG, "mm")
        c.text(x, top - r - 10, clean(pname, 14), font(BOLD, 24), TEXT, "ms")
        c.text(x, top + 36, str(pts), font(BOLD, 36), TEXT, "ma")
        c.text(x, top + 78, "points", font(PIX, 17), MUTED, "ma")
    hero = sprites.image(sprites.hero(), 6)  # your squad's berry, sword up
    c.sprite(hero, 24, base - hero.height)
    boss = sprites.boss_image("dead" if game.outcome == "victory" else "angry", "lie" if game.mode == "lie" else "boss", 150)
    c.sprite(boss, 960 - 30 - boss.width, base - boss.height)
    c.rect(24, base, 912, 3, TRACK)
    c.text(480, base + 30, f"Weak spot: {clean(', '.join(weak), 50)}" if weak else "No weak spots this round",
           font(REG, 21), GOLD if weak else MUTED, "mm")
    return c.png()


@safe
def profile(p: dict) -> bytes:
    """Avatar, level, XP bar and stat tiles for /profile."""
    c = Canvas(960, 340)
    color = color_for(p["name"])
    c.glow(110, 110, 160, color, 80)
    initials = "".join(w[0] for w in clean(p["name"]).split()[:2]).upper() or "?"
    c.d.ellipse([c.p(40, 40), c.p(180, 180)], fill=color)
    c.text(110, 110, initials, font(BOLD, 54), (255, 255, 255), "mm")
    lvl, title, start, nxt = progress.level_for(p["xp"])
    c.text(214, 52, clean(p["name"], 26), font(BOLD, 44))
    c.text(216, 112, f"LEVEL {lvl}  /  {clean(title).upper()}", font(PIX, 24), tint(color, 1.3))
    pct = 100 if not nxt else (p["xp"] - start) / (nxt - start) * 100
    c.rect(216, 152, 700, 22, TRACK, 11)
    c.rect(216, 152, max(22, 7 * pct), 22, GOLD, 11)
    nxt_title = next((clean(t) for need, t in progress.LEVELS if need == nxt), "")
    right = f"{p['xp'] - start} / {nxt - start} XP to {nxt_title}" if nxt else "MAX LEVEL"
    c.text(916, 140, right, font(REG, 19), MUTED, "rs")
    acc = f"{p['accuracy']}%" if p.get("accuracy") is not None else "-"
    tiles = [("GAMES", p.get("games", 0)), ("ACCURACY", acc), ("STREAK", p.get("daily", 0)),
             ("BADGES", len(p.get("badges") or [])), ("TOTAL XP", p["xp"])]
    for i, (label, value) in enumerate(tiles):
        x = 40 + i * 180
        c.rect(x, 210, 164, 96, PANEL, 12)
        c.text(x + 82, 238, str(value), font(BOLD, 36), TEXT, "mm")
        c.text(x + 82, 284, label, font(PIX, 17), MUTED, "mm")
    return c.png()
