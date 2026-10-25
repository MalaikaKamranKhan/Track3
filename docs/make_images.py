"""Renders the README pictures in docs/img from the real sprites and card code: .venv\\Scripts\\python docs\\make_images.py"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from squadbot import images, sprites  # noqa: E402
from squadbot.images import BOLD, PIX, REG, Canvas, font  # noqa: E402
from squadbot.store import Game, Question  # noqa: E402

OUT = ROOT / "docs" / "img"
KIT = sprites.ASSETS / "kit"
INK, CREAM, GOLD, BERRY, MUTED = (15, 16, 21), (246, 240, 228), (253, 227, 154), (184, 50, 110), (150, 154, 180)
POSES = [("idle", "default + avatar"), ("wave", "after /link"), ("victory", "boss defeated"), ("hit", "boss hits back"),
         ("thinking", "waiting on answers"), ("sleep", "/quiet mode")]


def kit(name: str, scale: int):
    return sprites.image(sprites.load_svg(KIT / f"{name}.svg"), scale)


def canvas(w: int, h: int, bg) -> Canvas:
    c = Canvas(w, h)
    c.rect(0, 0, w, h, bg)
    return c


def save(c: Canvas, name: str) -> None:
    (OUT / name).write_bytes(c.png())
    print("wrote", OUT / name)


def banner() -> None:
    c = canvas(1280, 420, INK)
    c.glow(930, 210, 260, (31, 111, 224), 90)
    c.glow(1130, 250, 160, sprites.PALETTES["lime"][1], 70)
    c.text(70, 70, "TEAM WILDBERRY  ·  DEVHACKS FALL 2026", font(PIX, 22), GOLD)
    c.text(64, 104, "Cramberry", font(PIX, 112), CREAM)
    y = 252
    for line in c.wrap("cram + cranberry. A pixel berry warrior that turns your Discord group chat into a "
                       "boss battle, and talks to your own Cubbie.", font(REG, 28), 600, 3):
        c.text(70, y, line, font(REG, 28), MUTED)
        y += 40
    hero = kit("poses/cramberry-idle", 9)
    c.sprite(hero, 700, 210 - hero.height / 2)
    boss = sprites.boss_image("angry", "lime", 192)
    c.sprite(boss, 1050, 330 - boss.height)
    c.text(1010, 200, "VS", font(PIX, 40), BERRY, "mm")
    save(c, "banner.png")


def poses() -> None:
    c = canvas(1280, 330, CREAM)
    step = 1280 / len(POSES)
    for i, (pose, use) in enumerate(POSES):
        cx = step * i + step / 2
        img = kit(f"poses/cramberry-{pose}", 5)
        c.sprite(img, cx - img.width / 2, 34)
        c.text(cx, 222, pose.upper(), font(PIX, 26), INK, "ma")
        c.text(cx, 262, use, font(REG, 21), (110, 98, 86), "ma")
    save(c, "poses.png")


def bosses() -> None:
    row = [(k, "angry", k.upper()) for k in sprites.FRUITS] + [("lie", "angry", "LIAR"), ("grape", "dead", "DEFEATED")]
    c = canvas(1280, 300, INK)
    step = 1280 / len(row)
    for i, (kind, mood, label) in enumerate(row):
        cx = step * i + step / 2
        if mood != "dead":
            c.glow(cx, 110, 80, sprites.PALETTES[kind][1], 60)
        img = sprites.boss_image(mood, kind, 144)
        c.sprite(img, cx - img.width / 2, 36)
        c.text(cx, 206, label, font(PIX, 24), CREAM if mood != "dead" else MUTED, "ma")
        c.text(cx, 242, "dragonfruit" if kind == "lie" else "grey when beaten" if mood == "dead" else "topic boss",
               font(REG, 19), MUTED, "ma")
    save(c, "bosses.png")


def kit_sheet() -> None:
    """Emoji, favicon and the 8-colour palette."""
    c = canvas(1280, 360, CREAM)
    items = [("emoji/sword", ":cramberry_sword:"), ("emoji/hp-heart", ":cramberry_hp:"),
             ("poses/cramberry-victory", ":cramberry_victory:"), ("poses/cramberry-wave", ":cramberry_wave:"),
             ("boss/topic-boss", ":cramberry_boss:"), ("favicon/favicon", "favicon")]
    step = 1280 / len(items)
    for i, (name, label) in enumerate(items):
        cx = step * i + step / 2
        img = kit(name, 3 if "favicon" not in name else 6)
        c.sprite(img, cx - img.width / 2, 28)
        c.text(cx, 136, label, font(BOLD, 19), INK, "ma")
    swatches = [("2b211b", "ink"), ("1b4fa8", "blue deep"), ("1f6fe0", "blue"), ("3a8cef", "blue mid"),
                ("f3a6b8", "blush"), ("ffffff", "white"), ("fde39a", "gold"), ("b8326e", "wildberry")]
    sw = 1280 / len(swatches)
    for i, (hexc, role) in enumerate(swatches):
        x = sw * i + 18
        c.rect(x, 200, sw - 36, 82, tuple(int(hexc[j:j + 2], 16) for j in (0, 2, 4)), 12)
        c.text(x, 296, f"#{hexc}", font(BOLD, 20), INK)
        c.text(x, 324, role, font(REG, 18), (110, 98, 86))
    save(c, "kit.png")


PANEL, LINE = (28, 30, 44), (58, 62, 88)


def arrow(c: Canvas, x0: float, x1: float, y: float, color, label: str = "", below: bool = False) -> None:
    """A dotted pixel arrow from x0 to x1 (either direction) with an optional label."""
    step = 12 if x1 > x0 else -12
    for x in range(int(x0), int(x1) - step, step):
        c.rect(min(x, x + step / 2), y - 3, 6, 6, color)
    tip = x1
    for i in range(4):  # stepped arrowhead
        dx = -step / 12 * i * 6
        c.rect(min(tip + dx, tip + dx - step / 2), y - 3 - i * 6, 6, 6 + i * 12, color)
    if label:
        c.text((x0 + x1) / 2, y + (16 if below else -16), label, font(REG, 19), MUTED, "ma" if below else "ms")


def berry() -> None:
    """The original berry, the hero with its sword, and the evil twin every boss is built from."""
    c = canvas(1280, 380, CREAM)
    tiles = [("THE BERRY", "the original avatar", None), ("CRAMBERRY", "sword up on the podium", "hero"),
             ("THE EVIL TWIN", "every topic boss", "boss")]
    for i, (title, sub, what) in enumerate(tiles):
        cx = 213 + i * 427
        if what is None:
            c.rect(cx - 120, 28, 240, 240, GOLD, 18)
            img = sprites.image(sprites.mascot(), 9)
        elif what == "hero":
            img = sprites.image(sprites.hero(), 8)
        else:
            img = sprites.boss_image("angry", "grape", 216)
        c.sprite(img, cx - img.width / 2, 148 - img.height / 2)
        c.text(cx, 290, title, font(PIX, 28), INK, "ma")
        c.text(cx, 330, sub, font(REG, 21), (110, 98, 86), "ma")
        if i < 2:
            c.text(cx + 213, 140, "→", font(BOLD, 44), BERRY, "mm")
    save(c, "berry.png")


def flow() -> None:
    """How it fits together: your phone, the Cramberry server, the group chat."""
    c = canvas(1280, 560, INK)
    c.glow(640, 280, 260, (31, 111, 224), 60)
    panels = [(40, "YOUR PHONE", "private", "poses/cramberry-wave",
               ["Your Cubbie (iMessage)", "builds battles from Canvas", "asks before posting", "texts your private recap"]),
              (470, "CRAMBERRY SERVER", "games + AI", "poses/cramberry-thinking",
               ["battles, Two Truths, Explain It", "questions from Gemini / Claude", "HTTPS API for Cubbie",
                "your misses stay private"]),
              (900, "GROUP CHAT", "shared", "boss",
               ["Discord: /battle, /lie, /explain", "picture cards + A-D buttons", "squad HP, crits, podium",
                "'im cooked' rallies the squad"])]
    for x, title, tag, art, lines in panels:
        c.rect(x, 40, 340, 480, PANEL, 22)
        c.rect(x, 40, 340, 6, BERRY if x == 900 else (31, 111, 224), 3)
        c.text(x + 28, 72, title, font(PIX, 26), CREAM)
        c.text(x + 28, 108, tag, font(REG, 19), GOLD)
        img = sprites.boss_image("angry", "lime", 120) if art == "boss" else kit(art, 4)
        c.sprite(img, x + 170 - img.width / 2, 146)
        y = 300
        for line in lines:
            c.rect(x + 30, y + 9, 8, 8, GOLD)
            c.text(x + 50, y, line, font(REG, 20), (214, 216, 230))
            y += 48
    arrow(c, 384, 466, 250, GOLD, "")
    arrow(c, 466, 384, 330, (31, 111, 224), "")
    arrow(c, 814, 896, 250, GOLD, "")
    arrow(c, 896, 814, 330, (31, 111, 224), "")
    for x, top, bottom in ((425, "skill + key", "your recap"), (855, "cards", "answers")):
        c.text(x, 222, top, font(REG, 16), MUTED, "ms")
        c.text(x, 352, bottom, font(REG, 16), MUTED, "ma")
    save(c, "flow.png")


def battle_flow() -> None:
    """One battle, start to finish."""
    c = canvas(1280, 330, INK)
    steps = [("poses/cramberry-hit", "IM COOKED", "someone panics in chat"),
             ("emoji/sword", "/BATTLE", "the squad picks the topic"),
             ("poses/cramberry-thinking", "ANSWER A-D", "crits, 50/50, wagers"),
             ("dead", "BOSS DOWN", "or it wipes the squad"),
             ("poses/cramberry-wave", "RECAP", "Cubbie texts your misses")]
    step = 1280 / len(steps)
    for i, (art, title, sub) in enumerate(steps):
        cx = step * i + step / 2
        img = sprites.boss_image("dead", "grape", 128) if art == "dead" else kit(art, 4)
        c.sprite(img, cx - img.width / 2, 40)
        c.text(cx, 196, title, font(PIX, 26), CREAM, "ma")
        c.text(cx, 236, sub, font(REG, 19), MUTED, "ma")
        if i < len(steps) - 1:
            arrow(c, cx + 82, cx + step - 82, 104, GOLD)
    c.text(640, 292, "2 minutes, the whole squad, one boss", font(PIX, 20), GOLD, "ma")
    save(c, "battle-flow.png")


def avatar() -> None:
    """Discord app + bot icon: the idle pose on cream, 1024 px (upload it in the Developer Portal)."""
    from PIL import Image
    img = Image.new("RGBA", (1024, 1024), CREAM + (255,))
    img.alpha_composite(kit("poses/cramberry-idle", 32))
    img.convert("RGB").save(OUT / "avatar.png")
    print("wrote", OUT / "avatar.png")


def cards() -> None:
    def q(i):
        return Question(f"Question {i}", ["A", "B", "C", "D"], 0, "")

    def game(topic, **kw):
        return Game("g", "s", topic, [q(i) for i in range(5)], **kw)

    board = [("1", "Malaika", 300), ("2", "Ynos", 200), ("3", "Dhanush", 100)]
    shots = {
        "card-battle.png": images.battle(game("recursion", current=1), "The Recursion Boss", "MISS", images.RED),
        "card-hurt.png": images.battle(game("tcp protocol stack", hp=30, current=3), "The Tcp Protocol Stack Boss", "CRIT!"),
        "card-liar.png": images.battle(game("caches", hp=70, mode="lie"), "Two Truths & a Lie: Caches"),
        "card-defeated.png": images.battle(game("sorting", hp=0, outcome="victory", current=4), "The Sorting Boss"),
        "card-victory.png": images.results(game("floating point", hp=0, outcome="victory"), "The Floating Point Boss",
                                           board, ["rounding"]),
        "card-wiped.png": images.results(game("CPU caches", squad_hp=0, outcome="wiped"), "The CPU Caches Boss",
                                         board[:1], ["associativity"]),
    }
    for name, png in shots.items():
        (OUT / name).write_bytes(png)
        print("wrote", OUT / name)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for make in (banner, berry, poses, bosses, flow, battle_flow, kit_sheet, avatar, cards):
        make()
