"""Study session polls (/plan): time slots, votes, locking and reminders. Times are the bot computer's local time."""
from __future__ import annotations

import re
import secrets
import time
from datetime import datetime, timedelta

from .cards import Button, Card, esc
from .store import Squad, Store

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
TIME_RE = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", re.I)


def parse_slot(text: str, now: datetime | None = None) -> datetime | None:
    """'tue 7pm', 'tomorrow 6:30pm', 'today 21:00', 'tonight 8', '10/28 7pm'. None if it can't be read."""
    now = now or datetime.now()
    t = text.strip().lower()
    day = None
    m = re.search(r"\b(\d{1,2})/(\d{1,2})\b", t)
    if m:
        try:
            day = now.replace(month=int(m.group(1)), day=int(m.group(2))).date()
        except ValueError:
            return None
        if day < now.date():
            day = day.replace(year=day.year + 1)
        t = t.replace(m.group(0), " ")
    elif re.search(r"\b(today|tonight)\b", t):
        day = now.date()
    elif "tomorrow" in t or "tmrw" in t:
        day = (now + timedelta(days=1)).date()
    else:
        for i, name in enumerate(DAYS):
            if re.search(rf"\b{name}", t):
                ahead = (i - now.weekday()) % 7 or 7
                day = (now + timedelta(days=ahead)).date()
                break
    tm = TIME_RE.search(t)
    if not tm:
        return None
    hour, minute, ampm = int(tm.group(1)), int(tm.group(2) or 0), (tm.group(3) or "").lower()
    if ampm == "pm" and hour < 12:
        hour += 12
    elif ampm == "am" and hour == 12:
        hour = 0
    elif not ampm and 1 <= hour <= 8:   # "tonight 8", "tue 7": students mean evening
        hour += 12
    if hour > 23 or minute > 59:
        return None
    if day is None:
        day = now.date()
        if datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute) <= now:
            day += timedelta(days=1)
    return datetime.combine(day, datetime.min.time()).replace(hour=hour, minute=minute)


def label(dt: datetime, now: datetime | None = None) -> str:
    now = now or datetime.now()
    clock = dt.strftime("%I:%M %p").lstrip("0").replace(":00 ", " ")
    if dt.date() == now.date():
        day = "Today"
    elif dt.date() == (now + timedelta(days=1)).date():
        day = "Tomorrow"
    else:
        day = dt.strftime("%a %b ") + str(dt.day)
    return f"{day} {clock}"


def default_slots(now: datetime | None = None) -> list[datetime]:
    """The next three evenings at 7 pm (today only if it's more than an hour away)."""
    now = now or datetime.now()
    start = now.replace(hour=19, minute=0, second=0, microsecond=0)
    if start - now < timedelta(hours=1):
        start += timedelta(days=1)
    return [start + timedelta(days=i) for i in range(3)]


def create(store: Store, squad: Squad, topic: str, course: str, by_id: str, by_name: str, times: str = "",
           now: datetime | None = None) -> tuple[dict | None, str]:
    now = now or datetime.now()
    slots = []
    for part in re.split(r"[,;|]|\bor\b", times or ""):
        if part.strip():
            dt = parse_slot(part, now)
            if dt is None:
                return None, f"I couldn't read \"{part.strip()}\". Try times like: tue 7pm, tomorrow 6:30pm, 10/28 8pm"
            if dt <= now:
                return None, f"\"{part.strip()}\" is in the past."
            slots.append(dt)
    slots = sorted(set(slots))[:4] or default_slots(now)
    plan = {"id": secrets.token_hex(3), "topic": topic[:80], "course": course, "by": str(by_id), "by_name": by_name,
            "slots": [{"label": label(s, now), "ts": s.timestamp()} for s in slots],
            "votes": {str(i): [] for i in range(len(slots))}, "status": "open", "chosen": None,
            "reminded": [], "created": time.time()}
    with store.lock:
        squad.plans = [p for p in squad.plans if p["status"] == "open" or p.get("chosen_ts", 0) > time.time() - 86400]
        squad.plans.append(plan)
        squad.plans = squad.plans[-10:]
        store.save()
    return plan, ""


def get(squad: Squad, plan_id: str) -> dict | None:
    return next((p for p in squad.plans if p["id"] == plan_id), None)


def toggle_vote(store: Store, squad: Squad, plan: dict, slot: int, uid: str, name: str) -> bool:
    """Returns True if the user is now going to that slot."""
    with store.lock:
        voters = plan["votes"].setdefault(str(slot), [])
        squad.members.setdefault(str(uid), name)
        if str(uid) in voters:
            voters.remove(str(uid))
            going = False
        else:
            voters.append(str(uid))
            going = True
        store.save()
    return going


def best_slot(plan: dict) -> int:
    return max(range(len(plan["slots"])), key=lambda i: (len(plan["votes"].get(str(i), [])), -i))


def lock(store: Store, squad: Squad, plan: dict, slot: int | None = None) -> dict:
    with store.lock:
        slot = best_slot(plan) if slot is None else slot
        plan["status"], plan["chosen"] = "locked", slot
        plan["chosen_ts"] = plan["slots"][slot]["ts"]
        store.save()
    return plan


def going(plan: dict, squad: Squad) -> list[tuple[str, str]]:
    slot = plan["chosen"] if plan["chosen"] is not None else best_slot(plan)
    return [(u, squad.members.get(u, "someone")) for u in plan["votes"].get(str(slot), [])]


def card(plan: dict, squad: Squad) -> Card:
    lines = []
    for i, s in enumerate(plan["slots"]):
        voters = [squad.members.get(u, "someone") for u in plan["votes"].get(str(i), [])]
        mark = "📌" if plan["chosen"] == i else "🗓️"
        who = f" · {esc(', '.join(voters))}" if voters else ""
        lines.append(f"{mark} **{s['label']}** · {len(voters)} going{who}")
    if plan["status"] == "locked":
        s = plan["slots"][plan["chosen"]]
        return Card(f"📌 Study session locked · {s['label']}", f"**{esc(plan['topic'])}**\n\n" + "\n".join(lines),
                    "good", footer="I'll ping everyone 30 min before and at the start · linked Cubbies can add it "
                                   "to your calendar")
    return Card(f"📆 When should we study {plan['topic'][:50]}?",
                f"Tap every time that works for you.\n\n" + "\n".join(lines), "calm",
                footer=f"Started by {plan['by_name']} · they lock it in when ready")


def buttons(plan: dict, token_for) -> list[Button]:
    if plan["status"] != "open":
        return []
    out = [Button(f"{s['label']} ({len(plan['votes'].get(str(i), []))})", token_for("plan_vote", plan["id"], i),
                  "secondary", row=i // 2) for i, s in enumerate(plan["slots"])]
    out.append(Button("📌 Lock it in", token_for("plan_lock", plan["id"]), "success", row=3))
    return out


def due_reminders(squad: Squad, now: float | None = None) -> list[tuple[dict, str]]:
    """[(plan, 'soon' | 'start')] for locked plans whose reminder time has come and hasn't been sent."""
    now = now or time.time()
    out = []
    for p in squad.plans:
        if p["status"] != "locked":
            continue
        ts = p["chosen_ts"]
        if "start" not in p["reminded"] and ts <= now < ts + 3600:
            out.append((p, "start"))
        elif "soon" not in p["reminded"] and ts - 1800 <= now < ts:
            out.append((p, "soon"))
    return out
