"""All state lives in one JSON file. Plenty for a hackathon; swap for a database later."""
from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from . import config

log = logging.getLogger("squad.store")


@dataclass
class Question:
    prompt: str
    options: list[str]          # 2-4 options (Two Truths & a Lie uses 3 statements)
    answer: int                 # index of the right option
    explanation: str = ""
    topic: str = ""             # sub-topic, used for weak-spot tracking


@dataclass
class Game:
    id: str
    squad_id: str
    topic: str
    questions: list[Question]
    source: str = "ai"          # "ai", or "cubbie:<name>" when a student's Cubbie sent it
    mode: str = "boss"          # boss | lie | daily
    course: str = ""
    seconds: int = 25           # answer time per question
    current: int = 0
    status: str = "running"     # running | done
    outcome: str = ""           # victory | survived | wiped
    hp: float = 100.0           # boss HP
    squad_hp: float = 100.0     # the squad's HP (the boss hits back)
    # answers[q_index][user_id] = [choice, seconds_from_question_start]
    answers: dict[str, dict[str, list]] = field(default_factory=dict)
    scores: dict[str, int] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    streaks: dict[str, int] = field(default_factory=dict)       # current right-answer streak per player
    best_streaks: dict[str, int] = field(default_factory=dict)
    fifty_used: bool = False
    removed: dict[str, list[int]] = field(default_factory=dict)  # q_index -> options removed by 50/50
    wagers: dict[str, float] = field(default_factory=dict)       # user -> fraction of points wagered on the final
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0


@dataclass
class Squad:
    id: str                     # "<platform>:<chat id>"
    platform: str
    chat_id: str
    name: str
    watching: bool = True
    members: dict[str, str] = field(default_factory=dict)          # user_id -> display name
    weak: dict[str, dict[str, int]] = field(default_factory=dict)  # user_id -> {topic: misses}
    totals: dict[str, int] = field(default_factory=dict)           # user_id -> all-time battle points
    last_nudge: float = 0.0
    game_ids: list[str] = field(default_factory=list)
    # course snapshots shared by each linked member's Cubbie: user_id -> {"at": ts, "courses": [...]}
    snapshots: dict[str, dict] = field(default_factory=dict)
    notes: list[dict] = field(default_factory=list)       # [{"name", "course", "text", "by", "at"}]
    nudged: list[str] = field(default_factory=list)        # suggestion keys already posted, never repeated
    # progress
    xp: dict[str, int] = field(default_factory=dict)
    badges: dict[str, list[str]] = field(default_factory=dict)
    stats: dict[str, dict[str, int]] = field(default_factory=dict)  # user -> {"games","correct","answered",...}
    user_daily: dict[str, dict] = field(default_factory=dict)       # user -> {"streak": n, "last": "YYYY-MM-DD"}
    daily: dict = field(default_factory=dict)  # {"time": "HH:MM", "last_posted": day, "streak": n, "last": day}
    radar: dict = field(default_factory=lambda: {"enabled": True, "time": "09:00", "last": ""})
    plans: list[dict] = field(default_factory=list)
    last_topic: str = ""
    last_course: str = ""


@dataclass
class Link:
    key: str                    # the secret the student saves in Cubbie as SQUAD_API_KEY
    squad_id: str
    user_id: str
    name: str
    created_at: float = field(default_factory=time.time)
    inbox: list[dict] = field(default_factory=list)  # things waiting for the student's Cubbie
    requests: list[dict] = field(default_factory=list)  # squad asks for a battle: {"id", "topic", "course", "by", "at"}


def _game_from(d: dict) -> Game:
    d = dict(d)
    d["questions"] = [Question(**q) for q in d["questions"]]
    known = Game.__dataclass_fields__
    return Game(**{k: v for k, v in d.items() if k in known})


def _from(cls, d: dict):
    known = cls.__dataclass_fields__
    return cls(**{k: v for k, v in d.items() if k in known})


class Store:
    def __init__(self, path: Path | None = None):
        self.path = path or (config.DATA_DIR / "state.json")
        self.lock = threading.RLock()
        self.squads: dict[str, Squad] = {}
        self.games: dict[str, Game] = {}
        self.links: dict[str, Link] = {}
        self._load()

    # persistence -----------------------------------------------------------
    def _load(self) -> None:
        if not self.path.is_file():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            log.exception("state file unreadable; starting fresh (old file kept as .broken)")
            try:
                self.path.replace(self.path.with_suffix(".broken"))
            except OSError:
                pass
            return
        self.squads = {k: _from(Squad, v) for k, v in raw.get("squads", {}).items()}
        self.games = {k: _game_from(v) for k, v in raw.get("games", {}).items()}
        self.links = {k: _from(Link, v) for k, v in raw.get("links", {}).items()}
        for g in self.games.values():  # a restart ends any game that was mid-flight
            if g.status == "running":
                g.status = "done"

    def save(self) -> bool:
        """Write state atomically. Never raises: on Windows another program (antivirus, an editor, OneDrive) can
        briefly lock the file, so retry a few times and otherwise log and carry on. A failed save must never
        crash a battle."""
        with self.lock:
            try:
                data = json.dumps({
                    "squads": {k: asdict(v) for k, v in self.squads.items()},
                    "games": {k: asdict(v) for k, v in self.games.items()},
                    "links": {k: asdict(v) for k, v in self.links.items()},
                }, indent=1)
            except (TypeError, ValueError):
                log.exception("state could not be serialized; not saved")
                return False
            last: Exception | None = None
            for attempt in range(6):
                tmp = self.path.with_name(f"state.{os.getpid()}.{attempt}.tmp")
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    tmp.write_text(data, encoding="utf-8")
                    os.replace(tmp, self.path)
                    return True
                except OSError as exc:
                    last = exc
                    time.sleep(0.05 * (attempt + 1))
            log.warning("could not save state (%s); will try again on the next change", last)
            return False

    # squads ----------------------------------------------------------------
    def squad(self, platform: str, chat_id, name: str = "") -> Squad:
        sid = f"{platform}:{chat_id}"
        with self.lock:
            sq = self.squads.get(sid)
            if not sq:
                sq = Squad(id=sid, platform=platform, chat_id=str(chat_id), name=name or "study squad")
                self.squads[sid] = sq
                self.save()
            elif name and sq.name != name:
                sq.name = name
            return sq

    def add_member(self, squad: Squad, user_id, name: str) -> None:
        with self.lock:
            squad.members[str(user_id)] = name

    # links -----------------------------------------------------------------
    def create_link(self, squad: Squad, user_id, name: str) -> Link:
        with self.lock:
            for link in self.links.values():  # one key per person per squad
                if link.squad_id == squad.id and link.user_id == str(user_id):
                    return link
            key = "sq_" + secrets.token_urlsafe(18)
            link = Link(key=key, squad_id=squad.id, user_id=str(user_id), name=name)
            self.links[key] = link
            self.save()
            return link

    def links_for(self, squad_id: str) -> list[Link]:
        return [l for l in self.links.values() if l.squad_id == squad_id]

    def link_for_user(self, squad_id: str, user_id) -> Link | None:
        for l in self.links_for(squad_id):
            if l.user_id == str(user_id):
                return l
        return None

    def push_inbox(self, link: Link, item: dict) -> None:
        with self.lock:
            link.inbox.append(item)
            link.inbox = link.inbox[-20:]
            self.save()

    def take_inbox(self, link: Link, keep: bool = False) -> list[dict]:
        with self.lock:
            items = list(link.inbox)
            if not keep:
                link.inbox.clear()
                self.save()
            return items

    # games -----------------------------------------------------------------
    def new_game(self, squad: Squad, topic: str, questions: list[Question], source: str = "ai", mode: str = "boss",
                 course: str = "", seconds: int | None = None) -> Game:
        with self.lock:
            game = Game(id=secrets.token_hex(4), squad_id=squad.id, topic=topic, questions=questions, source=source,
                        mode=mode, course=course, seconds=seconds or config.QUESTION_SECONDS)
            self.games[game.id] = game
            squad.game_ids.append(game.id)
            squad.last_topic, squad.last_course = topic, course or squad.last_course
            self.save()
            return game

    def active_game(self, squad_id: str) -> Game | None:
        sq = self.squads.get(squad_id)
        if not sq:
            return None
        for gid in reversed(sq.game_ids):
            g = self.games.get(gid)
            if g and g.status == "running":
                return g
        return None


store = Store()
