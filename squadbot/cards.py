"""Every message the bot sends is a Card. Discord renders it as a colored embed.

Card text uses a small Markdown subset: **bold**, *italic*, `code`, ~~strike~~. Wrap anything that came from a user
or the AI in esc() so stray * or _ show up as written.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import config, images, progress
from .engine import LETTERS, defeated, group_weak_topics, leaderboard, perfect_players, wants_wager
from .store import Game, Squad

COLORS = {"boss": 0xD85A30, "good": 0x1D9E75, "bad": 0xE24B4A, "info": 0x5865F2, "gold": 0xEF9F27,
          "calm": 0x7F77DD, "lie": 0xD4537E, "explain": 0x378ADD, "focus": 0x639922}
MEDALS = ["🥇", "🥈", "🥉"]


@dataclass
class Card:
    title: str
    body: str = ""
    color: str = "info"
    fields: list[tuple[str, str, bool]] = field(default_factory=list)  # (name, value, inline)
    footer: str = ""
    image: bytes | None = None  # optional picture (PNG) shown big inside the card


@dataclass
class Button:
    label: str
    token: str               # runner action token
    style: str = "primary"   # primary | secondary | success | danger
    row: int = 0


def esc(s) -> str:
    return re.sub(r"([\\*_`~|>])", r"\\\1", str(s))


def plain(card: Card) -> str:
    """Card as plain text (tests, logs, fallbacks)."""
    parts = [card.title, card.body] + [f"{n}: {v}" for n, v, _ in card.fields] + [card.footer]
    text = "\n".join(p for p in parts if p)
    return re.sub(r"\\(.)", r"\1", text.replace("**", "").replace("~~", ""))


# shared bits ---------------------------------------------------------------------

def bar(pct: float, full: str = "🟥", width: int = 10) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return full * filled + "⬛" * (width - filled) + f"  {round(pct)}%"


def boss_name(game_or_topic) -> str:
    if isinstance(game_or_topic, Game):
        if game_or_topic.mode == "lie":
            return "The Liar"
        topic = game_or_topic.topic
    else:
        topic = game_or_topic
    words = [w for w in re.split(r"[\s\-:]+", topic) if w and w.lower() not in {"the", "a", "an", "on", "of"}]
    core = " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in words[:3]) or "Study"
    return f"The {core} Boss"


def _hp_fields(game: Game) -> list[tuple[str, str, bool]]:
    return [("👹 Boss HP", bar(game.hp, "🟥"), True), ("🛡️ Squad HP", bar(game.squad_hp, "🟩"), True)]


def _source_line(game: Game) -> str:
    who = game.source.split(":", 1)[1] if game.source.startswith("cubbie:") else ""
    return f"📲 **{esc(who)}'s Cubbie** built this from their course material.\n" if who else ""


# battles -----------------------------------------------------------------------

def intro(game: Game) -> Card:
    course = f" · {game.course}" if game.course else ""
    if game.mode == "lie":
        card = Card(f"🕵️ Two Truths & a Lie · {game.topic[:60]}{course}",
                    _source_line(game) + "Each round has **three statements**. Two are true. Find the **lie**.\n"
                    "Right answers damage The Liar. Wrong ones let it hit back.",
                    "lie", _hp_fields(game),
                    f"{len(game.questions)} rounds · {game.seconds}s each · 🎲 one 50/50 per game")
        card.image = images.battle(game, boss_name(game))
        return card
    if game.mode == "daily":
        return Card(f"📅 Daily Duel · {game.topic[:60]}{course}",
                    "One question a day. Answer right to keep your 🔥 streak alive.",
                    "gold", footer=f"Open for {_dur(game.seconds)}")
    card = Card(f"⚔️ {boss_name(game)} has appeared!{course}",
                _source_line(game) + "Everyone answers. Every right answer damages the boss, "
                "and every wrong one lets it hit the squad back.\n🔥 3 in a row = critical hit.",
                "boss", _hp_fields(game),
                f"{len(game.questions)} questions · {game.seconds}s each · 🎲 one 50/50 per battle"
                + (" · 💰 final wager" if wants_wager(game) else ""))
    card.image = images.battle(game, boss_name(game))
    return card


def _dur(seconds: int) -> str:
    return f"{seconds // 60} min" if seconds >= 120 else f"{seconds}s"


def question(game: Game, qi: int) -> Card:
    q = game.questions[qi]
    removed = set(game.removed.get(str(qi), []))
    lines = []
    for i, opt in enumerate(q.options):
        line = f"**{LETTERS[i]}** · {esc(opt)}"
        lines.append(f"~~{line}~~" if i in removed else line)
    total = len(game.questions)
    final = qi == total - 1 and total > 1 and game.mode != "daily"
    head = "Which one is the lie?" if game.mode == "lie" else esc(q.prompt)
    title = (f"🕵️ Round {qi + 1}/{total}" if game.mode == "lie" else
             f"📅 Today's question" if game.mode == "daily" else f"⚔️ Q{qi + 1}/{total} · {boss_name(game)}")
    if final:
        title = "💥 FINAL STRIKE · " + title
    tips = [f"⏱️ {_dur(game.seconds)}"]
    if game.mode != "daily" and not game.fifty_used:
        tips.append("🎲 50/50 ready")
    if final and game.wagers:
        tips.append(f"💰 {sum(1 for f in game.wagers.values() if f)} wagers riding")
    hot = [game.names.get(u, u) for u, s in game.streaks.items() if s >= 2]
    if hot and game.mode != "daily":
        tips.append("🔥 " + ", ".join(hot[:3]) + " on a streak")
    return Card(title, f"**{head}**\n\n" + "\n".join(lines),
                {"lie": "lie", "daily": "gold"}.get(game.mode, "boss"),
                _hp_fields(game) if game.mode != "daily" else [], " · ".join(tips))


def reveal(game: Game, s: dict) -> Card:
    q = s["question"]
    right = f"{LETTERS[q.answer]}) {q.options[q.answer]}"
    label = "The lie" if game.mode == "lie" else "Answer"
    if not s["answered"]:
        title, color = f"⌛ Q{s['index'] + 1} · nobody answered", "bad"
    elif not s["correct"]:
        title, color = f"❌ Q{s['index'] + 1} · nobody got it", "bad"
    else:
        title, color = f"✅ Q{s['index'] + 1} · {len(s['correct'])} of {s['answered']} got it", "good"
    lines = [f"**{label}: {esc(right)}**"]
    if q.explanation:
        lines.append(f"💡 {esc(q.explanation)}")
    if game.mode != "daily":
        if s["correct"]:
            crit = f"  ⚡ CRIT by {esc(', '.join(s['crits']))}" if s["crits"] else ""
            lines.append(f"💥 **-{round(s['damage'])} boss HP** from {esc(', '.join(s['correct']))}{crit}")
        if s["boss_hit"]:
            lines.append(f"👹 The boss hits back: **-{s['boss_hit']} squad HP**")
    for name, delta, frac in s.get("wagers", []):
        lines.append(f"💰 {esc(name)} wagered {'ALL IN' if frac >= 1 else 'half'}: **{'+' if delta > 0 else ''}{delta}**")
    card = Card(title, "\n".join(lines), color, _hp_fields(game) if game.mode != "daily" else [])
    if game.mode != "daily":
        if s["crits"]:
            stamp, tone = "CRIT!", images.GOLD
        elif s["correct"]:
            stamp, tone = f"-{round(s['damage'])} HP", images.GOLD
        else:
            stamp, tone = "MISS", images.RED
        card.image = images.battle(game, boss_name(game), stamp, tone)
    return card


def results(squad: Squad, game: Game, awards: dict[str, dict]) -> Card:
    board = leaderboard(game)
    name = boss_name(game)
    if game.outcome == "victory":
        title, color = f"🏆 {name} defeated! GG squad", "good"
    elif game.outcome == "wiped":
        title, color = f"💀 {name} wiped the squad", "bad"
    else:
        title, color = f"😤 {name} survived with {round(game.hp)}% HP", "bad"
    rows = []
    for i, (uid, pname, pts) in enumerate(board[:8]):
        medal = MEDALS[i] if i < 3 else f"{i + 1}."
        gain = awards.get(uid, {}).get("xp", 0)
        rows.append(f"{medal} **{esc(pname)}** · {pts} pts · +{gain} XP")
    fields = [("🏅 Leaderboard", "\n".join(rows) or "No one played this round.", False)]
    extras = []
    for uid, a in awards.items():
        who = esc(game.names.get(uid, squad.members.get(uid, "someone")))
        if a.get("badges"):
            extras.append(f"{who} earned {progress.badge_line(a['badges'])}")
        if a.get("level_up"):
            extras.append(f"{who} leveled up to **{a['level_up']}**")
    if extras:
        fields.append(("✨ Unlocked", "\n".join(extras), False))
    weak = group_weak_topics(game)
    fields.append(("🎯 Squad weak spot", esc(", ".join(weak)) if weak else "None this round 📈", True))
    if board:
        fields.append(("⭐ MVP", esc(board[0][1]), True))
    card = Card(title, "", color, fields, "Linked players: your Cubbie has your private recap · /profile for your stats")
    card.image = images.results(game, name, board, weak)
    return card


def wager_prompt(game: Game) -> Card:
    return Card("💰 Final strike incoming!",
                "Bet your points on the last question. Right doubles your stake, wrong loses it.\n"
                f"Pick in the next {round(config.WAGER_SECONDS)}s or you play it safe.", "gold")


def daily_results(game: Game, streaks: dict, awards: dict[str, dict]) -> Card:
    q = game.questions[0]
    bucket = game.answers.get("0", {})
    right = [u for u, (c, _) in bucket.items() if c == q.answer]
    wrong = [u for u in bucket if u not in right]
    lines = [f"**Answer: {esc(LETTERS[q.answer] + ') ' + q.options[q.answer])}**"]
    if q.explanation:
        lines.append(f"💡 {esc(q.explanation)}")
    rows = [f"✅ {esc(game.names.get(u, u))} · 🔥 {streaks.get(u, 1)}" for u in right]
    rows += [f"❌ {esc(game.names.get(u, u))}" for u in wrong]
    fields = [("Today's duelists", "\n".join(rows) or "Nobody played today 😴", False)]
    squad_streak = streaks.get("_squad", 0)
    if squad_streak:
        fields.append(("🔥 Squad streak", f"{squad_streak} day{'s' if squad_streak != 1 else ''}", True))
    unlocked = [f"{esc(game.names.get(u, u))} earned {progress.badge_line(a['badges'])}"
                for u, a in awards.items() if a.get("badges")]
    if unlocked:
        fields.append(("✨ Unlocked", "\n".join(unlocked), False))
    return Card("📅 Daily Duel results", "\n".join(lines), "gold", fields, "Same time tomorrow · /daily to change it")


def battle_awards(game: Game) -> dict[str, dict]:
    """XP and badge keys each player earned in a finished game (not yet applied)."""
    out = {}
    perfect = set(perfect_players(game))
    for uid, pts in game.scores.items():
        badges = []
        if defeated(game) and game.mode == "boss":
            badges.append("slayer")
        if uid in perfect:
            badges.append("liedetector" if game.mode == "lie" else "perfect")
        if game.best_streaks.get(uid, 0) >= 5:
            badges.append("onfire")
        last = len(game.questions) - 1
        if game.wagers.get(uid, 0) >= 1 and game.answers.get(str(last), {}).get(uid, [None])[0] == \
                game.questions[last].answer and pts > 0:
            badges.append("highroller")
        out[uid] = {"xp": 10 + pts // 5 + (25 if defeated(game) else 0), "badges": badges}
    return out


# offers, insights, help ---------------------------------------------------------

def offer(topic: str, course: str) -> Card:
    where = f" for {course}" if course and course.lower() not in topic.lower() else ""
    return Card("👀 Study moment spotted",
                f"Sounds like the squad is prepping for **{esc(topic)}**{esc(where)}.\n"
                "Quick boss battle? Takes about 2 minutes.", "calm")


def suggestion(text: str) -> Card:
    return Card("💡 Perfect time for a battle", esc(text), "calm")


def squad_board(squad: Squad) -> Card:
    rows = progress.ranking(squad)
    if not rows:
        return Card("📊 Squad leaderboard", "No battles yet. Start one with /battle <topic>.", "info")
    lines = []
    for i, (uid, name, xp) in enumerate(rows[:10]):
        lvl, title, _, _ = progress.level_for(xp)
        medal = MEDALS[i] if i < 3 else f"{i + 1}."
        streak = squad.user_daily.get(uid, {}).get("streak", 0)
        lines.append(f"{medal} **{esc(name)}** · {title} · {xp} XP" + (f" · 🔥{streak}" if streak else ""))
    squad_streak = squad.daily.get("streak", 0)
    return Card("📊 Squad leaderboard", "\n".join(lines), "gold",
                footer=f"Squad daily streak: 🔥 {squad_streak}" if squad_streak else "Play the Daily Duel to start a streak")


def profile_card(squad: Squad, uid: str) -> Card:
    p = progress.profile(squad, uid)
    acc = f"{p['accuracy']}%" if p["accuracy"] is not None else "—"
    badges = progress.badge_line(p["badges"]) or "None yet. Beat a boss to earn your first!"
    fields = [("Level", f"**{p['title']}** · Lv {p['level']}\n{p['bar']}", False),
              ("🎮 Games", str(p["games"]), True), ("🎯 Accuracy", acc, True), ("🔥 Daily streak", str(p["daily"]), True),
              ("🧠 Explains", str(p["explains"]), True), ("🍅 Focus", str(p["focus"]), True),
              ("⭐ XP", str(p["xp"]), True), ("🏅 Badges", badges, False)]
    if p["weak"]:
        fields.append(("📉 Work on", esc(", ".join(p["weak"])), False))
    card = Card(f"👤 {p['name']}", "", "calm", fields, f"{squad.name}")
    card.image = images.profile(p)
    return card


def help_card() -> Card:
    return Card(f"⚔️ {config.BOT_NAME} · your study squad's game host",
                "Turn the group chat into a study session. Link your Cubbie and battles come from your own courses.",
                "info", [
                    ("🎮 Games", "/battle <topic> · boss battle\n/lie <topic> · Two Truths & a Lie\n"
                                "/explain <topic> · teach it back, AI grades it\n/daily · today's Daily Duel", False),
                    ("📚 Study", "/plan <topic> · pick a study session time\n/focus [minutes] · group Pomodoro\n"
                                "/radar · what's due this week\n/notes · upload slides or notes (PDF)", False),
                    ("🏅 Progress", "/profile · your level and badges\n/leaderboard · squad XP ranking", False),
                    ("📲 Cubbie", "/link · connect your Cubbie\n/ask_cubbie <topic> · ask linked Cubbies for a battle\n"
                                 f"/insights · what {config.BOT_NAME} knows about your courses", False),
                    ("🔒 Privacy", "/quiet · stop reading the chat · /watch · turn it back on", False)],
                "Tip: say \"midterm thursday, im cooked\" and see what happens 👀")


def link_card(key: str) -> Card:
    return Card("🔗 Your private squad key", f"`{key}`\n\nDon't share it.", "calm", [
        ("Connect your Cubbie", "1. Install the squad-link Skill on Cubbie\n2. Text Cubbie **link my study squad**\n"
                                "3. Paste this key on Cubbie's secure page (never in the chat)", False)],
        f"Server: {config.PUBLIC_URL}")


def notice(title: str, body: str = "", color: str = "info") -> Card:
    return Card(title, body, color)
