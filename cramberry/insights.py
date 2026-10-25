"""What the squad is studying: course snapshots from each member's Cubbie, uploaded notes, battle requests,
and the "right moment" suggestions built from them. Pure logic plus store updates; no chat I/O here."""
from __future__ import annotations

import re
import secrets
import time
from collections import defaultdict
from datetime import date, datetime

from .store import Link, Squad, Store

SNAPSHOT_FRESH_HOURS = 72
EXAM_WORDS = re.compile(r"\b(exam|midterm|final|quiz|test)\b", re.I)
MAX_NOTES = 12
MAX_NOTE_CHARS = 15000


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s).lower()).strip()


def _clip(s, n) -> str:
    return str(s or "").strip()[:n]


# snapshots -----------------------------------------------------------------

def clean_snapshot(raw: dict) -> dict:
    """Keep only topic names, titles, dates and done/not-done. Raises ValueError on a malformed snapshot."""
    if not isinstance(raw, dict) or not isinstance(raw.get("courses"), list):
        raise ValueError("snapshot needs a list of courses")
    courses = []
    for c in raw["courses"][:8]:
        if not isinstance(c, dict) or not c.get("code"):
            raise ValueError("each course needs a code, like CSE 230")
        upcoming = []
        for u in (c.get("upcoming") or [])[:15]:
            due = _clip(u.get("due"), 25)
            if due:
                try:
                    date.fromisoformat(due[:10])
                except ValueError:
                    raise ValueError(f"due date {due!r} must start with YYYY-MM-DD") from None
            upcoming.append({"title": _clip(u.get("title"), 80), "kind": _clip(u.get("kind"), 20),
                             "due": due[:10], "topic": _clip(u.get("topic"), 60)})
        courses.append({
            "code": _clip(c["code"], 20).upper(),
            "name": _clip(c.get("name"), 80),
            "topics": [_clip(t, 60) for t in (c.get("topics") or [])[:10] if str(t).strip()],
            "upcoming": [u for u in upcoming if u["title"]],
            "submitted": [{"title": _clip(s.get("title"), 80), "topic": _clip(s.get("topic"), 60)}
                          for s in (c.get("submitted") or [])[:15] if isinstance(s, dict) and s.get("title")],
        })
    return {"at": int(time.time()), "courses": courses}


def save_snapshot(store: Store, squad: Squad, link: Link, snapshot: dict) -> None:
    with store.lock:
        squad.snapshots[link.user_id] = snapshot
        squad.members.setdefault(link.user_id, link.name)
        store.save()


def fresh_snapshots(squad: Squad, now: float | None = None) -> dict[str, dict]:
    now = now or time.time()
    return {u: s for u, s in squad.snapshots.items() if now - s.get("at", 0) < SNAPSHOT_FRESH_HOURS * 3600}


# notes ---------------------------------------------------------------------

def add_note(store: Store, squad: Squad, name: str, course: str, text: str, by: str) -> dict:
    note = {"name": _clip(name, 80), "course": _clip(course, 20).upper(), "text": text[:MAX_NOTE_CHARS],
            "by": _clip(by, 40), "at": int(time.time())}
    with store.lock:
        squad.notes.append(note)
        squad.notes = squad.notes[-MAX_NOTES:]
        store.save()
    return note


def material_for(squad: Squad, topic: str, course: str = "") -> str:
    """Pick the uploaded notes that best match a topic, so battles come from the squad's own material."""
    words = {w for w in _norm(f"{topic} {course}").split() if len(w) > 2}
    scored = []
    for n in squad.notes:
        hay = _norm(f"{n['name']} {n['course']} {n['text'][:4000]}")
        score = sum(hay.count(w) for w in words)
        if course and n["course"] and _norm(n["course"]) == _norm(course):
            score += 5
        if score:
            scored.append((score, n["at"], n))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    return "\n\n".join(f"[{n['name']}]\n{n['text']}" for _, _, n in scored[:2])[:12000]


# requests to Cubbies ---------------------------------------------------------

def ask_cubbies(store: Store, squad: Squad, topic: str, course: str, by: str) -> int:
    """Leave a battle request in every linked member's mailbox. Returns how many Cubbies were asked."""
    rid = secrets.token_hex(4)
    links = store.links_for(squad.id)
    with store.lock:
        for link in links:
            link.requests = [r for r in link.requests if time.time() - r["at"] < 24 * 3600][-4:]
            link.requests.append({"id": rid, "topic": _clip(topic, 80), "course": _clip(course, 20).upper(),
                                  "by": _clip(by, 40), "squad": squad.name, "at": int(time.time())})
        store.save()
    return len(links)


def close_request(store: Store, squad_id: str, request_id: str) -> None:
    """Once one Cubbie answers a request, it's done for everyone."""
    with store.lock:
        for link in store.links_for(squad_id):
            link.requests = [r for r in link.requests if r["id"] != request_id]
        store.save()


def decline_request(store: Store, link: Link, request_id: str) -> None:
    with store.lock:
        link.requests = [r for r in link.requests if r["id"] != request_id]
        store.save()


# right-moment suggestions ----------------------------------------------------

def _days_until(day: str, today: date) -> int | None:
    try:
        return (date.fromisoformat(day[:10]) - today).days
    except ValueError:
        return None


def suggestions(squad: Squad, now: float | None = None) -> list[dict]:
    """Moments worth a battle, best first. Each: {"key", "topic", "course", "text"}."""
    now = now or time.time()
    today = datetime.fromtimestamp(now).date()
    snaps = fresh_snapshots(squad, now)
    name = lambda uid: squad.members.get(uid, "someone")  # noqa: E731
    out = []

    takers: dict[str, set] = defaultdict(set)              # course -> members taking it
    submitted: dict[tuple, dict] = {}                      # (course, title) -> {"who", "topic", "title"}
    exams: dict[tuple, dict] = {}
    topics: dict[str, set] = defaultdict(set)
    for uid, snap in snaps.items():
        for c in snap["courses"]:
            takers[c["code"]].add(uid)
            topics[c["code"]].update(c["topics"])
            for s in c["submitted"]:
                k = (c["code"], _norm(s["title"]))
                submitted.setdefault(k, {"who": set(), "topic": s["topic"], "title": s["title"]})["who"].add(uid)
            for u in c["upcoming"]:
                days = _days_until(u["due"], today) if u["due"] else None
                if days is None or not 0 <= days <= 3:
                    continue
                if not (EXAM_WORDS.search(u["kind"]) or EXAM_WORDS.search(u["title"])):
                    continue
                k = (c["code"], _norm(u["title"]))
                e = exams.setdefault(k, {"who": set(), "title": u["title"], "topic": u["topic"], "days": days})
                e["who"].add(uid)

    for (course, title), e in sorted(exams.items(), key=lambda kv: kv[1]["days"]):
        if len(e["who"]) < 2:
            continue
        when = {0: "today", 1: "tomorrow"}.get(e["days"], f"in {e['days']} days")
        topic = e["topic"] or ", ".join(sorted(topics[course])[:2]) or e["title"]
        out.append({"key": f"exam:{course}:{title}", "topic": topic, "course": course,
                    "text": f"⏰ {len(e['who'])} of you have the {course} {e['title']} {when}. "
                            f"Battle on {topic} tonight?"})

    for (course, _), s in submitted.items():
        everyone = takers[course]
        if len(s["who"]) >= 2 and s["who"] >= everyone:
            topic = s["topic"] or s["title"]
            who = "Both of you" if len(everyone) == 2 else f"All {len(everyone)} of you"
            out.append({"key": f"done:{course}:{_norm(s['title'])}", "topic": topic, "course": course,
                        "text": f"🎯 {who} submitted {course} {s['title']} ({topic}). "
                                f"Perfect time to lock it in with a boss battle?"})

    misses: dict[str, int] = defaultdict(int)
    for per_user in squad.weak.values():
        for t, n in per_user.items():
            misses[t] += n
    for t, n in sorted(misses.items(), key=lambda kv: -kv[1])[:1]:
        if n >= 3:
            out.append({"key": f"weak:{_norm(t)}:{n // 3}", "topic": t, "course": "",
                        "text": f"📉 The squad has missed {t} {n} times in battles. Rematch to beat it for good?"})

    return [s for s in out if s["key"] not in squad.nudged]


def mark_nudged(store: Store, squad: Squad, key: str) -> None:
    with store.lock:
        squad.nudged.append(key)
        squad.nudged = squad.nudged[-200:]
        squad.last_nudge = time.time()
        store.save()


def _code(s: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s).upper())


def course_info(squad: Squad, course: str) -> dict | None:
    """Merge what every member's Cubbie shared about one course code."""
    if not course:
        return None
    want = _code(course)
    info = None
    for uid, snap in fresh_snapshots(squad).items():
        for c in snap["courses"]:
            if _code(c["code"]) != want:
                continue
            if info is None:
                info = {"code": c["code"], "name": c["name"], "topics": [], "upcoming": [], "who": []}
            info["name"] = info["name"] or c["name"]
            info["topics"] += [t for t in c["topics"] if t not in info["topics"]]
            info["upcoming"] += [u for u in c["upcoming"] if u not in info["upcoming"]]
            info["who"].append(squad.members.get(uid, "someone"))
    return info


def resolve(squad: Squad, topic: str, course: str = "") -> tuple[str, str, str]:
    """(topic, course, context) for a game. Uses the Cubbie snapshots so 'CSE230' means this squad's CSE 230,
    and a bare course code becomes that course's topics this week."""
    from .engine import course_in  # local import: engine stays free of insights
    topic = (topic or "").strip()
    course = (course or course_in(topic)).strip().upper()
    info = course_info(squad, course)
    if not info:
        return topic or "this week's material", course, ""
    if not topic or _code(topic) == _code(course):
        focus = ", ".join(info["topics"][:3])
        topic = f"{info['code']} {info['name']}".strip() + (f": {focus}" if focus else "")
    ctx = [f"{info['code']} {info['name']}".strip()]
    if info["topics"]:
        ctx.append("this week: " + ", ".join(info["topics"][:5]))
    soon = [f"{u['title']} ({u['kind'] or 'due'}) on {u['due']}" + (f" about {u['topic']}" if u["topic"] else "")
            for u in info["upcoming"][:3]]
    if soon:
        ctx.append("coming up: " + "; ".join(soon))
    return topic[:80], info["code"], ". ".join(ctx)


def upcoming(squad: Squad, days: int = 7, today: date | None = None) -> list[dict]:
    """Everything due in the next `days` days across the squad, grouped, soonest first."""
    today = today or date.today()
    grouped: dict[tuple, dict] = {}
    for uid, snap in fresh_snapshots(squad).items():
        for c in snap["courses"]:
            for u in c["upcoming"]:
                d = _days_until(u["due"], today) if u["due"] else None
                if d is None or not 0 <= d <= days:
                    continue
                k = (c["code"], _norm(u["title"]), u["due"])
                g = grouped.setdefault(k, {"course": c["code"], "title": u["title"], "kind": u["kind"],
                                           "due": u["due"], "topic": u["topic"], "days": d, "who": []})
                g["who"].append(squad.members.get(uid, "someone"))
    return sorted(grouped.values(), key=lambda g: (g["days"], g["course"]))


def when_label(days: int) -> str:
    return {0: "today", 1: "tomorrow"}.get(days, f"in {days} days")


def overview(squad: Squad):
    """Card summary of what the bot knows, for /insights."""
    from .cards import Card, esc
    snaps = fresh_snapshots(squad)
    fields = []
    if not snaps:
        body = "No Cubbie snapshots yet. Linked members: text your Cubbie **check my squad**."
    else:
        body = f"From {len(snaps)} linked Cubbie{'s' if len(snaps) != 1 else ''}."
        by_course: dict[str, dict] = defaultdict(lambda: {"who": set(), "topics": [], "name": ""})
        for uid, snap in snaps.items():
            for c in snap["courses"]:
                b = by_course[c["code"]]
                b["who"].add(squad.members.get(uid, "someone"))
                b["name"] = b["name"] or c["name"]
                b["topics"] += [t for t in c["topics"] if t not in b["topics"]]
        due = upcoming(squad, 7)
        for code, b in sorted(by_course.items())[:12]:
            lines = [f"👥 {esc(', '.join(sorted(b['who'])))}"]
            if b["topics"]:
                lines.append(f"📖 {esc(', '.join(b['topics'][:4]))}")
            for g in [g for g in due if g["course"] == code][:2]:
                lines.append(f"⏰ {esc(g['title'])} {when_label(g['days'])}")
            fields.append((f"📚 {code}" + (f" · {b['name'][:40]}" if b["name"] else ""), "\n".join(lines), True))
    if squad.notes:
        fields.append(("📎 Notes", esc(", ".join(n["name"] for n in squad.notes[-5:])), False))
    misses: dict[str, int] = defaultdict(int)
    for per_user in squad.weak.values():
        for t, n in per_user.items():
            misses[t] += n
    if misses:
        top = sorted(misses.items(), key=lambda kv: -kv[1])[:3]
        fields.append(("📉 Squad weak spots", esc(", ".join(f"{t} ({n})" for t, n in top)), False))
    return Card("🧠 What I know about this squad", body, "calm", fields,
                "Shared by Cubbies: course codes, topics, due dates, done/not-done. No grades, no files.")
