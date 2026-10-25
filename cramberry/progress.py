"""XP, levels, badges and Daily Duel streaks."""
from __future__ import annotations

from datetime import date, timedelta

from .store import Squad, Store

LEVELS = [  # (xp needed, title)
    (0, "🐣 Freshman"), (100, "📗 Sophomore"), (300, "📘 Junior"), (600, "📙 Senior"),
    (1000, "🎓 Grad Student"), (1500, "🧑‍🏫 TA"), (2200, "🧪 Researcher"), (3000, "👑 Professor"),
]

BADGES = {
    "slayer": ("🗡️", "Boss Slayer", "Beat a boss"),
    "perfect": ("🎯", "Perfect Round", "Every answer right in a battle"),
    "onfire": ("🔥", "On Fire", "5 right answers in a row"),
    "liedetector": ("🕵️", "Lie Detector", "Spotted every lie in a round"),
    "professor": ("🧠", "Big Brain", "Scored 9+ in Explain It"),
    "highroller": ("💰", "High Roller", "Won an all-in wager"),
    "habit": ("📅", "Habit Builder", "3-day Daily Duel streak"),
    "deepwork": ("🍅", "Deep Work", "Finished 3 focus sessions"),
}


def level_for(xp: int) -> tuple[int, str, int, int]:
    """(level number, title, xp at this level's start, xp for the next level or 0 at max)."""
    idx = 0
    for i, (need, _) in enumerate(LEVELS):
        if xp >= need:
            idx = i
    nxt = LEVELS[idx + 1][0] if idx + 1 < len(LEVELS) else 0
    return idx + 1, LEVELS[idx][1], LEVELS[idx][0], nxt


def xp_bar(xp: int, width: int = 10) -> str:
    _, _, start, nxt = level_for(xp)
    if not nxt:
        return "🟨" * width + " MAX"
    filled = round((xp - start) / (nxt - start) * width)
    return "🟨" * filled + "⬛" * (width - filled) + f" {xp - start}/{nxt - start}"


def award(store: Store, squad: Squad, uid: str, xp: int = 0, badges: list[str] | tuple = ()) -> dict:
    """Give XP and badges. Returns {"xp": gained, "level_up": "title" or "", "badges": [new badge keys]}."""
    uid = str(uid)
    with store.lock:
        before = level_for(squad.xp.get(uid, 0))[0]
        squad.xp[uid] = squad.xp.get(uid, 0) + max(0, int(xp))
        after_lvl, title, _, _ = level_for(squad.xp[uid])
        have = squad.badges.setdefault(uid, [])
        new = [b for b in dict.fromkeys(badges) if b in BADGES and b not in have]
        have.extend(new)
        store.save()
    return {"xp": max(0, int(xp)), "level_up": title if after_lvl > before else "", "badges": new}


def badge_line(keys: list[str]) -> str:
    return " ".join(f"{BADGES[k][0]} {BADGES[k][1]}" for k in keys if k in BADGES)


def record_daily(store: Store, squad: Squad, day: date, correct: list[str], answered: list[str]) -> dict:
    """Update Daily Duel streaks. Returns {uid: streak} for everyone who answered, plus "_squad"."""
    today, yesterday = day.isoformat(), (day - timedelta(days=1)).isoformat()
    out = {}
    with store.lock:
        for uid in answered:
            rec = squad.user_daily.setdefault(uid, {"streak": 0, "last": ""})
            if uid in correct:
                if rec["last"] == today:
                    pass
                elif rec["last"] == yesterday:
                    rec["streak"] += 1
                else:
                    rec["streak"] = 1
                rec["last"] = today
            else:
                rec["streak"] = 0
            out[uid] = rec["streak"]
        if correct:
            d = squad.daily
            if d.get("last") == yesterday:
                d["streak"] = d.get("streak", 0) + 1
            elif d.get("last") != today:
                d["streak"] = 1
            d["last"] = today
        out["_squad"] = squad.daily.get("streak", 0) if squad.daily.get("last") in (today, yesterday) else 0
        store.save()
    return out


def profile(squad: Squad, uid: str) -> dict:
    uid = str(uid)
    xp = squad.xp.get(uid, 0)
    lvl, title, _, _ = level_for(xp)
    st = squad.stats.get(uid, {})
    answered, correct = st.get("answered", 0), st.get("correct", 0)
    weak = sorted(squad.weak.get(uid, {}).items(), key=lambda kv: -kv[1])[:3]
    return {
        "name": squad.members.get(uid, "player"), "xp": xp, "level": lvl, "title": title, "bar": xp_bar(xp),
        "badges": squad.badges.get(uid, []), "games": st.get("games", 0), "accuracy":
        round(100 * correct / answered) if answered else None, "explains": st.get("explains", 0),
        "focus": st.get("focus", 0), "daily": squad.user_daily.get(uid, {}).get("streak", 0),
        "weak": [t for t, _ in weak], "points": squad.totals.get(uid, 0),
    }


def ranking(squad: Squad) -> list[tuple[str, str, int]]:
    ids = set(squad.xp) | set(squad.totals)
    return sorted(((u, squad.members.get(u, u), squad.xp.get(u, 0)) for u in ids), key=lambda x: -x[2])
