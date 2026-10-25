"""Runs every game and feature in any chat app. Each app implements the small Adapter interface below and forwards
commands, button presses and chat messages here."""
from __future__ import annotations

import asyncio
import logging
import random
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from . import cards, config, engine, insights, llm, notes, planner, progress
from .cards import Button, Card, esc
from .store import Game, Squad, store

log = logging.getLogger("squad.runner")


class Adapter(Protocol):
    platform: str

    async def send(self, chat_id: str, card: Card, buttons: list[Button] | None = None,
                   mentions: list[tuple[str, str]] | None = None, reply_to: Any = None) -> Any: ...

    async def edit(self, chat_id: str, handle: Any, card: Card | None = None,
                   buttons: list[Button] | None = None) -> None: ...


@dataclass
class Reply:
    card: Card | None = None
    private: bool = False
    buttons: list[Button] = field(default_factory=list)


ADAPTERS: dict[str, Adapter] = {}
_asked: dict[str, tuple[int, float]] = {}       # game id -> (question index, time asked)
_qhandles: dict[str, Any] = {}                  # game id -> current question message
_recent: dict[str, list[str]] = {}              # squad id -> last messages, kept in memory only
_recent_authors: dict[str, list[str]] = {}      # squad id -> recent speakers, newest last
_moment_checks: dict[str, float] = {}
_panic_replies: dict[str, float] = {}           # squad id -> last "im cooked" reply
_starting: set[str] = set()                     # squads whose game is being generated
_explain: dict[str, dict] = {}                  # squad id -> running Explain It state
_focus: dict[str, dict] = {}                    # squad id -> running focus session
_actions: dict[str, tuple[str, tuple, float]] = {}


def register(adapter: Adapter) -> None:
    ADAPTERS[adapter.platform] = adapter


# helpers ------------------------------------------------------------------------

def token(kind: str, *data) -> str:
    now = time.time()
    if len(_actions) > 5000:
        for k in [k for k, (_, _, t) in _actions.items() if now - t > 86400]:
            _actions.pop(k, None)
    t = secrets.token_hex(5)
    _actions[t] = (kind, data, now)
    return t


def busy(squad: Squad) -> str:
    if squad.id in _starting:
        return "A game is loading in this chat. One sec!"
    if store.active_game(squad.id) or squad.id in _explain:
        return "A game is already running in this chat. Finish it first!"
    return ""


async def _safe(coro, what: str):
    try:
        return await coro
    except Exception:  # noqa: BLE001 - a failed send or edit should never kill a game
        log.exception("%s failed", what)
        return None


async def post(squad: Squad, card: Card, buttons: list[Button] | None = None,
               mentions: list[tuple[str, str]] | None = None, reply_to: Any = None):
    adapter = ADAPTERS.get(squad.platform)
    if not adapter:
        return None
    return await _safe(adapter.send(squad.chat_id, card, buttons, mentions, reply_to), "send")


async def edit(squad: Squad, handle: Any, card: Card | None = None, buttons: list[Button] | None = None):
    adapter = ADAPTERS.get(squad.platform)
    if adapter and handle is not None:
        await _safe(adapter.edit(squad.chat_id, handle, card, buttons), "edit")


def _note_author(squad: Squad, uid: str) -> None:
    lst = _recent_authors.setdefault(squad.id, [])
    if uid in lst:
        lst.remove(uid)
    lst.append(uid)
    del lst[:-12]


# quiz games (boss battle, Two Truths & a Lie, Daily Duel) --------------------------

async def start_game(squad: Squad, topic: str, mode: str = "boss", *, questions: list[dict] | None = None,
                     material: str = "", source: str = "ai", course: str = "",
                     seconds: int | None = None) -> tuple[Game | None, str]:
    """Create a game and run it in the background. Returns (game, error message)."""
    if squad.platform not in ADAPTERS:
        return None, f"{config.BOT_NAME} isn't running on {squad.platform} right now."
    err = busy(squad)
    if err:
        return None, err
    _starting.add(squad.id)
    try:
        topic, course, context = insights.resolve(squad, topic, course)
        if not questions and not material:
            material = insights.material_for(squad, topic, course)
        try:
            if questions:
                qs = engine.validate_questions(questions)
            elif mode == "lie":
                qs = engine.validate_questions(await llm.generate_lies(topic, material, context=context), options=3)
            elif mode == "daily":
                qs = engine.validate_questions(await llm.generate_questions(topic, material, n=1, context=context))
            else:
                qs = engine.validate_questions(await llm.generate_questions(topic, material, context=context))
        except Exception as exc:  # noqa: BLE001 - any LLM failure becomes one friendly line
            log.exception("could not build questions")
            return None, f"Couldn't make questions on {topic} right now ({type(exc).__name__}). Try again in a moment."
        if mode == "daily":
            qs = qs[:1]
        secs = seconds or (config.LIE_SECONDS if mode == "lie" else config.QUESTION_SECONDS)
        game = store.new_game(squad, topic, qs, source=source, mode=mode, course=course, seconds=secs)
    finally:
        _starting.discard(squad.id)
    asyncio.create_task(_run(squad, game))
    return game, ""


async def start_battle(squad: Squad, topic: str, *, questions: list[dict] | None = None, material: str = "",
                       source: str = "ai", course: str = "") -> tuple[Game | None, str]:
    """Boss battle (kept for the Cubbie API)."""
    return await start_game(squad, topic, "boss", questions=questions, material=material, source=source,
                            course=course)


def _answer_buttons(game: Game, qi: int) -> list[Button]:
    removed = set(game.removed.get(str(qi), []))
    out = [Button(engine.LETTERS[i], token("ans", game.id, qi, i), "primary", 0)
           for i in range(len(game.questions[qi].options)) if i not in removed]
    if game.mode != "daily" and not game.fifty_used:
        out.append(Button("🎲 50/50", token("fifty", game.id, qi), "secondary", 1))
    return out


async def _run(squad: Squad, game: Game) -> None:
    try:
        await post(squad, cards.intro(game))
        await asyncio.sleep(config.INTRO_PAUSE)
        players: set[str] = set(squad.members) if game.mode == "daily" else set()
        while game.status == "running":
            qi = game.current
            if engine.is_final(game, qi) and engine.wants_wager(game) and qi > 0:
                await _wager_phase(squad, game)
            _asked[game.id] = (qi, time.time())
            handle = await post(squad, cards.question(game, qi), _answer_buttons(game, qi))
            if handle is None and qi == 0:
                raise RuntimeError("could not post the first question")
            _qhandles[game.id] = handle
            await _wait_for_answers(game, qi, players)
            players |= set(game.answers.get(str(qi), {}))
            summary = engine.close_question(store, squad, game)
            _asked.pop(game.id, None)
            await edit(squad, handle, cards.question(game, qi), [])
            await post(squad, cards.reveal(game, summary), reply_to=handle)
            if not summary["done"]:
                await asyncio.sleep(config.REVEAL_PAUSE)
        await _finish(squad, game)
    except Exception:  # noqa: BLE001
        log.exception("game %s crashed", game.id)
        game.status = "done"
        store.save()
        await post(squad, cards.notice("😵 Something broke mid-game", "Start a new one with /battle.", "bad"))
    finally:
        _asked.pop(game.id, None)
        _qhandles.pop(game.id, None)


async def _wager_phase(squad: Squad, game: Game) -> None:
    btns = [Button("🛡️ Play safe", token("wager", game.id, 0.0), "secondary"),
            Button("💸 Bet half", token("wager", game.id, 0.5), "primary"),
            Button("🔥 ALL IN", token("wager", game.id, 1.0), "danger")]
    handle = await post(squad, cards.wager_prompt(game), btns)
    await asyncio.sleep(config.WAGER_SECONDS)
    bets = [f"{esc(game.names.get(u, u))}: {'ALL IN' if f >= 1 else 'half'}" for u, f in game.wagers.items() if f]
    await edit(squad, handle, cards.notice("💰 Wagers locked", "\n".join(bets) or "Everyone played it safe.", "gold"),
               [])


async def _wait_for_answers(game: Game, qi: int, players: set[str]) -> None:
    """Wait for the timer, or close early once everyone who has played so far has answered."""
    start = time.time()
    while time.time() - start < game.seconds and game.status == "running":
        await asyncio.sleep(0.5)
        answered = set(game.answers.get(str(qi), {}))
        if players and players <= answered and time.time() - start > 3:
            return


async def _finish(squad: Squad, game: Game) -> None:
    if game.mode == "daily":
        q = game.questions[0]
        bucket = game.answers.get("0", {})
        right = [u for u, (c, _) in bucket.items() if c == q.answer]
        streaks = progress.record_daily(store, squad, datetime.now().date(), right, list(bucket))
        awards = {}
        for uid in bucket:
            st = streaks.get(uid, 0)
            awards[uid] = progress.award(store, squad, uid, (30 + 5 * st) if uid in right else 5,
                                         ["habit"] if st >= 3 else [])
        await post(squad, cards.daily_results(game, streaks, awards))
        return
    engine.finish_game(store, squad, game)
    awards = {uid: progress.award(store, squad, uid, a["xp"], a["badges"])
              for uid, a in cards.battle_awards(game).items()}
    weak = (engine.group_weak_topics(game, 1) or [game.topic])[0]
    btns = [Button("🔁 Rematch weak spot", token("start", squad.id, "boss", weak, game.course), "success"),
            Button("🕵️ Spot the lie", token("start", squad.id, "lie", game.topic, game.course), "secondary"),
            Button("📆 Plan a session", token("plan_new", squad.id, game.topic, game.course), "secondary")]
    await post(squad, cards.results(squad, game, awards), btns)


def answer(game_id: str, qi: int, user_id, name: str, choice: int) -> str:
    game = store.games.get(game_id)
    if not game:
        return "closed"
    asked = _asked.get(game_id)
    if not asked or asked[0] != qi:
        return "closed"
    squad = store.squads[game.squad_id]
    store.add_member(squad, user_id, name)
    return engine.record_answer(store, game, qi, user_id, name, choice, asked[1])


# Explain It -------------------------------------------------------------------

async def start_explain(squad: Squad, topic: str, course: str, starter_id: str, starter_name: str) -> str:
    if squad.platform not in ADAPTERS:
        return f"{config.BOT_NAME} isn't running on {squad.platform} right now."
    err = busy(squad)
    if err:
        return err
    _starting.add(squad.id)
    try:
        topic, course, context = insights.resolve(squad, topic, course)
        material = insights.material_for(squad, topic, course)
        try:
            items = await llm.explain_items(topic, material, config.EXPLAIN_ROUNDS, context)
        except Exception as exc:  # noqa: BLE001
            log.exception("could not build explain items")
            return f"Couldn't set up Explain It on {topic} right now ({type(exc).__name__}). Try again in a moment."
        store.add_member(squad, starter_id, starter_name)
        order = [u for u in reversed(_recent_authors.get(squad.id, [])) if u in squad.members][:6]
        if str(starter_id) not in order:
            order.insert(0, str(starter_id))
        random.shuffle(order)
        state = {"topic": topic, "course": course, "items": items, "order": order, "scores": {}, "future": None,
                 "target": None, "open": False}
        _explain[squad.id] = state
    finally:
        _starting.discard(squad.id)
    asyncio.create_task(_run_explain(squad, state))
    return ""


async def _wait_explain(state: dict, seconds: float):
    fut = asyncio.get_running_loop().create_future()
    state["future"] = fut
    try:
        return await asyncio.wait_for(fut, seconds)
    except asyncio.TimeoutError:
        return None
    finally:
        state["future"] = None


async def _run_explain(squad: Squad, state: dict) -> None:
    try:
        await post(squad, Card(f"🎤 Explain It · {state['topic'][:60]}",
                               "I'll call on someone to explain a concept **in their own words**. The AI grades it "
                               "0-10 like a kind TA.\nIf they pass, it's **open floor** for half XP.",
                               "explain", footer=f"{len(state['items'])} rounds"))
        await asyncio.sleep(config.INTRO_PAUSE)
        for r, item in enumerate(state["items"]):
            target = state["order"][r % len(state["order"])] if state["order"] else None
            tname = squad.members.get(target, "someone") if target else "anyone"
            state.update(target=target, open=target is None)
            body = (f"**{esc(item['ask'])}**\n\n🎙️ {esc(tname)}, you're up! Type your explanation in the chat."
                    if target else f"**{esc(item['ask'])}**\n\nFirst good explanation wins.")
            await post(squad, Card(f"🎤 Round {r + 1}/{len(state['items'])} · {item['concept'][:60]}", body,
                                   "explain", footer=f"⏱️ {round(config.EXPLAIN_SECONDS)}s · say \"pass\" to pass"),
                       mentions=[(target, tname)] if target else None)
            got = await _wait_explain(state, config.EXPLAIN_SECONDS)
            half = False
            if got in (None, "pass") and target:
                state.update(open=True, target=None)
                half = True
                await post(squad, Card("🙋 Open floor!", f"{esc(tname)} passed. Anyone can explain "
                                       f"**{esc(item['concept'])}** for half XP.", "explain",
                                       footer=f"⏱️ {round(config.OPEN_FLOOR_SECONDS)}s"))
                got = await _wait_explain(state, config.OPEN_FLOOR_SECONDS)
            if got in (None, "pass"):
                pts = "\n".join(f"• {esc(k)}" for k in item["key_points"])
                await post(squad, Card("😶 Nobody took this one", f"A great answer covers:\n{pts}", "bad"))
            else:
                await _grade(squad, state, item, got, half)
            await asyncio.sleep(config.REVEAL_PAUSE)
        rows = sorted(state["scores"].items(), key=lambda kv: -kv[1]["score"])
        lines = [f"{cards.MEDALS[i] if i < 3 else f'{i + 1}.'} **{esc(v['name'])}** · {v['score']} pts"
                 for i, (_, v) in enumerate(rows)]
        btns = [Button("🎤 Another round", token("explain", squad.id, state["topic"], state["course"]), "success"),
                Button("⚔️ Battle this topic", token("start", squad.id, "boss", state["topic"], state["course"]),
                       "secondary")]
        await post(squad, Card("🎤 Explain It · final scores", "\n".join(lines) or "Nobody explained anything 😴",
                               "explain"), btns)
    except Exception:  # noqa: BLE001
        log.exception("explain game crashed")
        await post(squad, cards.notice("😵 Explain It broke", "Start a new one with /explain.", "bad"))
    finally:
        _explain.pop(squad.id, None)


async def _grade(squad: Squad, state: dict, item: dict, got: tuple, half: bool) -> None:
    uid, name, text = got
    try:
        g = await llm.grade_explanation(item["concept"], item["key_points"], text)
    except Exception:  # noqa: BLE001 - fall back to keyword grading if the model hiccups
        log.exception("grading failed")
        g = llm.fake_grade(item["key_points"], text)
    score = g["score"]
    xp = score * 8 // (2 if half else 1)
    a = progress.award(store, squad, uid, xp, ["professor"] if score >= 9 and not half else [])
    with store.lock:
        squad.stats.setdefault(uid, {})
        squad.stats[uid]["explains"] = squad.stats[uid].get("explains", 0) + 1
    s = state["scores"].setdefault(uid, {"name": name, "score": 0})
    s["score"] += score
    hit = [k for k in item["key_points"] if k not in g["missed"]]
    fields = []
    if hit:
        fields.append(("✅ You covered", "\n".join(f"• {esc(k)}" for k in hit), True))
    if g["missed"]:
        fields.append(("➕ Add next time", "\n".join(f"• {esc(k)}" for k in g["missed"]), True))
    extra = f" · {progress.badge_line(a['badges'])}" if a["badges"] else ""
    if a["level_up"]:
        extra += f" · leveled up to {a['level_up']}"
    color = "good" if score >= 8 else "gold" if score >= 5 else "bad"
    await post(squad, Card(f"🧠 {name}: {score}/10" + (" (open floor)" if half else ""), esc(g["feedback"]),
                           color, fields, f"+{xp} XP{extra}"))
    link = store.link_for_user(squad.id, uid)
    if link:
        store.push_inbox(link, {"type": "explain", "squad": squad.name, "concept": item["concept"], "score": score,
                                "feedback": g["feedback"], "missed": g["missed"], "at": int(time.time())})


def _capture_explain(squad: Squad, uid: str, name: str, body: str) -> bool:
    st = _explain.get(squad.id)
    fut = st and st.get("future")
    if not fut or fut.done():
        return False
    if not (st["open"] or st["target"] == uid):
        return False
    text = body.strip()
    if text.lower() in ("pass", "skip", "idk", "i pass") and st["target"] == uid:
        fut.set_result("pass")
        return True
    if len(text) >= 15:
        fut.set_result((uid, name, text))
        return True
    return False


# Daily Duel ----------------------------------------------------------------------

def _daily_topic(squad: Squad) -> tuple[str, str]:
    misses: dict[str, int] = {}
    for per_user in squad.weak.values():
        for t, n in per_user.items():
            misses[t] = misses.get(t, 0) + n
    if misses:
        return max(misses, key=misses.get), squad.last_course
    if squad.last_topic:
        return squad.last_topic, squad.last_course
    for snap in insights.fresh_snapshots(squad).values():
        for c in snap["courses"]:
            if c["topics"]:
                return random.choice(c["topics"]), c["code"]
    return "", ""


async def start_daily(squad: Squad, seconds: int, topic: str = "") -> str:
    course = ""
    if not topic:
        topic, course = _daily_topic(squad)
    if not topic:
        return "I don't know what you're studying yet. Play a /battle or link a Cubbie first."
    _, err = await start_game(squad, topic, "daily", course=course, seconds=seconds)
    return err


def _parse_clock(text: str) -> str | None:
    dt = planner.parse_slot(f"today {text}", datetime.now().replace(hour=0, minute=0))
    return dt.strftime("%H:%M") if dt else None


# focus sessions ------------------------------------------------------------------

def _focus_card(st: dict) -> Card:
    left = max(0, round((st["ends"] - time.time()) / 60))
    names = ", ".join(st["joined"].values())
    return Card(f"🍅 Focus session · {st['minutes']} min", f"Phones down, tabs closed. **{left} min** left."
                + (f"\nStudying: **{esc(st['topic'])}**" if st["topic"] else "") + f"\n\n👥 {esc(names)}",
                "focus", footer="Join to get pinged at the break · +20 XP for finishing")


async def start_focus(squad: Squad, uid: str, name: str, minutes: float, topic: str = "",
                      seconds: float | None = None) -> str:
    if squad.id in _focus:
        left = max(0, round((_focus[squad.id]["ends"] - time.time()) / 60))
        return f"A focus session is already running ({left} min left). Tap Join on it!"
    minutes = max(1, min(120, minutes))
    st = {"id": secrets.token_hex(3), "minutes": round(minutes), "ends": time.time() + minutes * 60,
          "joined": {str(uid): name}, "starter": str(uid), "topic": topic, "stop": asyncio.Event()}
    _focus[squad.id] = st
    st["handle"] = await post(squad, _focus_card(st), _focus_buttons(squad, st))
    asyncio.create_task(_run_focus(squad, st, seconds if seconds is not None else minutes * 60))
    return ""


def _focus_buttons(squad: Squad, st: dict) -> list[Button]:
    return [Button(f"🍅 Join ({len(st['joined'])})", token("focus_join", squad.id, st["id"]), "success"),
            Button("🛑 End", token("focus_end", squad.id, st["id"]), "secondary")]


async def _run_focus(squad: Squad, st: dict, seconds: float) -> None:
    try:
        try:
            await asyncio.wait_for(st["stop"].wait(), seconds)
            ended_early = True
        except asyncio.TimeoutError:
            ended_early = False
        await edit(squad, st.get("handle"), Card(f"🍅 Focus session · done", f"👥 {esc(', '.join(st['joined'].values()))}",
                                                 "focus"), [])
        if ended_early:
            await post(squad, cards.notice("🛑 Focus session ended early", "No XP this time. /focus to try again.",
                                           "bad"))
            return
        unlocked = []
        for uid in st["joined"]:
            with store.lock:
                squad.stats.setdefault(uid, {})
                squad.stats[uid]["focus"] = squad.stats[uid].get("focus", 0) + 1
                done = squad.stats[uid]["focus"]
            a = progress.award(store, squad, uid, 20, ["deepwork"] if done >= 3 else [])
            if a["badges"]:
                unlocked.append(f"{esc(st['joined'][uid])} earned {progress.badge_line(a['badges'])}")
        topic = st["topic"] or squad.last_topic
        btns = [Button(f"⚔️ Quick battle: {topic[:30]}", token("start", squad.id, "boss", topic, squad.last_course),
                       "success")] if topic else []
        body = "Stretch, grab water, back in 5. 💧\n+20 XP each" + ("\n" + "\n".join(unlocked) if unlocked else "")
        await post(squad, Card("⏰ Break time! Great focus, squad", body, "focus"), btns,
                   mentions=list(st["joined"].items()))
    finally:
        _focus.pop(squad.id, None)


# deadline radar, plans, scheduler -----------------------------------------------------

def radar_card(squad: Squad) -> tuple[Card, list[Button]]:
    items = insights.upcoming(squad, 7)
    if not items:
        return cards.notice("📡 Deadline radar", "Nothing due in the next 7 days that I know of. Linked members: "
                                                 "text your Cubbie **check my squad** to share deadlines.",
                            "info"), []
    lines = []
    for g in items[:10]:
        icon = "📝" if engine.STUDY_WORDS.search(f"{g['kind']} {g['title']}") and \
            any(w in f"{g['kind']} {g['title']}".lower() for w in ("exam", "midterm", "final", "quiz", "test")) else "📌"
        lines.append(f"{icon} **{insights.when_label(g['days']).capitalize()}** · {g['course']} {esc(g['title'])}"
                     f" · {esc(', '.join(g['who']))}")
    soon = next((g for g in items if any(w in f"{g['kind']} {g['title']}".lower()
                                         for w in ("exam", "midterm", "final", "quiz", "test"))), items[0])
    topic = soon["topic"] or f"{soon['course']} {soon['title']}"
    btns = [Button(f"⚔️ Battle: {topic[:30]}", token("start", squad.id, "boss", topic, soon["course"]), "success"),
            Button("📆 Plan a session", token("plan_new", squad.id, topic, soon["course"]), "secondary")]
    return Card("📡 Deadline radar · next 7 days", "\n".join(lines), "gold",
                footer="From linked Cubbies · /radar any time"), btns


async def create_plan(squad: Squad, topic: str, course: str, uid: str, name: str, times: str = "") -> str:
    plan, err = planner.create(store, squad, topic or squad.last_topic or "study session", course, uid, name, times)
    if err:
        return err
    await post(squad, planner.card(plan, squad), planner.buttons(plan, lambda *a: token(a[0], squad.id, *a[1:])))
    return ""


async def _remind(squad: Squad, plan: dict, kind: str) -> None:
    who = planner.going(plan, squad)
    s = plan["slots"][plan["chosen"]]
    if kind == "soon":
        card = Card(f"⏰ Study session in 30 min · {s['label']}", f"**{esc(plan['topic'])}**\nSee you there!", "calm")
        btns = []
    else:
        card = Card(f"📚 Study session starting now", f"**{esc(plan['topic'])}**\nKick it off with a warm-up:",
                    "good")
        btns = [Button("⚔️ Warm-up battle", token("start", squad.id, "boss", plan["topic"], plan["course"]), "success"),
                Button("🍅 25-min focus", token("focus_new", squad.id, plan["topic"]), "secondary")]
    await post(squad, card, btns, mentions=who)


async def scheduler() -> None:
    """Daily Duels, the morning deadline radar and study-session reminders."""
    while True:
        try:
            await _tick()
        except Exception:  # noqa: BLE001
            log.exception("scheduler tick failed")
        await asyncio.sleep(config.SCHEDULER_SECONDS)


async def _tick(now: datetime | None = None) -> None:
    now = now or datetime.now()
    today, hhmm = now.date().isoformat(), now.strftime("%H:%M")
    for squad in list(store.squads.values()):
        if squad.platform not in ADAPTERS:
            continue
        t = squad.daily.get("time")
        if t and hhmm >= t and squad.daily.get("last_posted") != today and not busy(squad):
            squad.daily["last_posted"] = today
            store.save()
            err = await start_daily(squad, config.DAILY_SECONDS)
            if err:
                log.info("daily duel skipped for %s: %s", squad.id, err)
        r = squad.radar
        if r.get("enabled", True) and hhmm >= r.get("time", "09:00") and r.get("last") != today \
                and insights.fresh_snapshots(squad):
            r["last"] = today
            store.save()
            if insights.upcoming(squad, 7):
                card, btns = radar_card(squad)
                await post(squad, card, btns)
        for plan, kind in planner.due_reminders(squad, now.timestamp()):
            plan["reminded"].append(kind)
            store.save()
            await _remind(squad, plan, kind)


# buttons -------------------------------------------------------------------------

ANSWER_ACK = {"locked": "Locked in {l} ✅", "changed": "Switched to {l} 🔁", "closed": "Too late, that question closed ⏱️",
              "removed": "That option was knocked out by the 50/50 🎲"}


async def press(tok: str, user_id, name: str, handle: Any = None) -> str | None:
    """A button was pressed. Returns a short private acknowledgement (or None)."""
    entry = _actions.get(tok)
    if not entry:
        return "That button expired. Run the command again."
    kind, data, _ = entry
    uid = str(user_id)
    if kind == "ans":
        game_id, qi, choice = data
        return ANSWER_ACK.get(answer(game_id, qi, uid, name, choice), "Got it").format(l=engine.LETTERS[choice])
    if kind == "fifty":
        game_id, qi = data
        game = store.games.get(game_id)
        squad = store.squads.get(game.squad_id) if game else None
        if not game or not squad:
            return "That game is over."
        dropped = engine.use_fifty(store, game, qi)
        if dropped is None:
            return "The 50/50 is already used (or that question closed)."
        await edit(squad, _qhandles.get(game_id), cards.question(game, qi), _answer_buttons(game, qi))
        await post(squad, cards.notice(f"🎲 {name} used the 50/50!",
                                       f"Knocked out {' and '.join(engine.LETTERS[i] for i in dropped)}.", "calm"))
        return "Two wrong answers gone 🎲" if len(dropped) == 2 else "One wrong answer gone 🎲"
    if kind == "wager":
        game_id, frac = data
        game = store.games.get(game_id)
        if not game or not engine.set_wager(store, game, uid, name, frac):
            return "Wagers are closed."
        return {0.0: "Playing it safe 🛡️", 0.5: "Half your points on the line 💸"}.get(frac, "ALL IN 🔥 Good luck")

    squad = store.squads.get(data[0]) if data else None
    if not squad:
        return "That chat isn't set up anymore."
    if kind == "start":
        _, mode, topic, course = data
        if busy(squad):
            return busy(squad)
        await edit(squad, handle, None, [])
        asyncio.create_task(_start_from_button(squad, mode, topic, course, name))
        return "Starting! ⚔️"
    if kind == "explain":
        _, topic, course = data
        await edit(squad, handle, None, [])
        asyncio.create_task(_explain_from_button(squad, topic, course, uid, name))
        return "Let's go 🎤"
    if kind == "ask":
        _, topic, course = data
        await edit(squad, handle, None, [])
        await post(squad, cards.notice("📲 Asking your Cubbies", esc(ask_cubbies(squad, topic, course, name)), "calm"))
        return None
    if kind == "dismiss":
        await edit(squad, handle, None, [])
        return "No worries. /battle whenever you're ready."
    if kind == "plan_new":
        _, topic, course = data
        err = await create_plan(squad, topic, course, uid, name)
        return err or "Poll posted 📆"
    if kind == "plan_vote":
        _, plan_id, slot = data
        plan = planner.get(squad, plan_id)
        if not plan or plan["status"] != "open":
            return "That poll is closed."
        going = planner.toggle_vote(store, squad, plan, slot, uid, name)
        await edit(squad, handle, planner.card(plan, squad),
                   planner.buttons(plan, lambda *a: token(a[0], squad.id, *a[1:])))
        return f"You're in for {plan['slots'][slot]['label']} ✅" if going else "Removed ❎"
    if kind == "plan_lock":
        _, plan_id = data
        plan = planner.get(squad, plan_id)
        if not plan or plan["status"] != "open":
            return "Already locked."
        if plan["by"] != uid:
            return f"Only {plan['by_name']} can lock it. Vote for your times!"
        if not any(plan["votes"].values()):
            return "Nobody has voted yet."
        planner.lock(store, squad, plan)
        await edit(squad, handle, planner.card(plan, squad), [])
        s = plan["slots"][plan["chosen"]]
        for vuid, vname in planner.going(plan, squad):
            link = store.link_for_user(squad.id, vuid)
            if link:
                store.push_inbox(link, {"type": "session", "squad": squad.name, "topic": plan["topic"],
                                        "label": s["label"], "start": datetime.fromtimestamp(s["ts"]).isoformat(),
                                        "with": [n for u, n in planner.going(plan, squad) if u != vuid],
                                        "at": int(time.time())})
        return "Locked 📌"
    if kind == "focus_join":
        _, fid = data
        st = _focus.get(squad.id)
        if not st or st["id"] != fid:
            return "That focus session is over."
        st["joined"][uid] = name
        await edit(squad, st.get("handle"), _focus_card(st), _focus_buttons(squad, st))
        return "You're in 🍅 I'll ping you at the break."
    if kind == "focus_end":
        _, fid = data
        st = _focus.get(squad.id)
        if not st or st["id"] != fid:
            return "That focus session is over."
        if st["starter"] != uid:
            return "Only the person who started it can end it."
        st["stop"].set()
        return "Ending it."
    if kind == "focus_new":
        _, topic = data
        err = await start_focus(squad, uid, name, 25, topic)
        return err or "Focus started 🍅"
    return None


async def _start_from_button(squad: Squad, mode: str, topic: str, course: str, name: str) -> None:
    await post(squad, cards.notice(f"{'🕵️' if mode == 'lie' else '⚔️'} {name} started a "
                                   f"{'round of Two Truths & a Lie' if mode == 'lie' else 'boss battle'}",
                                   f"Topic: **{esc(topic)}**", "calm"))
    _, err = await start_game(squad, topic, mode, course=course)
    if err:
        await post(squad, cards.notice("Couldn't start it", esc(err), "bad"))


async def _explain_from_button(squad: Squad, topic: str, course: str, uid: str, name: str) -> None:
    err = await start_explain(squad, topic, course, uid, name)
    if err:
        await post(squad, cards.notice("Couldn't start Explain It", esc(err), "bad"))


# commands ------------------------------------------------------------------------

def ask_cubbies(squad: Squad, topic: str, course: str, by: str) -> str:
    n = insights.ask_cubbies(store, squad, topic, course, by)
    if not n:
        return "Nobody here has linked a Cubbie yet. Use /link to connect yours."
    return (f"Asked {n} linked Cubbie{'s' if n > 1 else ''} for a {topic} battle from their course material. "
            f"The first person to say yes on their phone posts it here.")


async def command(squad: Squad, name: str, uid, uname: str, args: dict | None = None) -> Reply:
    """Every slash command from every app lands here."""
    args = args or {}
    uid = str(uid)
    store.add_member(squad, uid, uname)
    _note_author(squad, uid)
    topic, course = (args.get("topic") or "").strip(), (args.get("course") or "").strip()
    if name in ("battle", "lie"):
        if not topic and not course:
            return Reply(cards.notice("What topic?", f"Try: /{name} caches", "info"), private=True)
        game, err = await start_game(squad, topic or course, "lie" if name == "lie" else "boss", course=course)
        if err:
            return Reply(cards.notice("Couldn't start it", esc(err), "bad"), private=True)
        verb = "started Two Truths & a Lie on" if name == "lie" else "summoned a boss on"
        return Reply(cards.notice(f"{'🕵️' if name == 'lie' else '⚔️'} {uname} {verb} {game.topic[:60]}!", "",
                                  "lie" if name == "lie" else "boss"))
    if name == "explain":
        if not topic and not course:
            return Reply(cards.notice("What topic?", "Try: /explain caches", "info"), private=True)
        err = await start_explain(squad, topic or course, course, uid, uname)
        return Reply(cards.notice("Couldn't start it", esc(err), "bad"), private=True) if err else \
            Reply(cards.notice(f"🎤 {uname} started Explain It!", "", "explain"))
    if name == "daily":
        at = (args.get("at") or "").strip().lower()
        if at in ("off", "stop", "none"):
            squad.daily.pop("time", None)
            store.save()
            return Reply(cards.notice("📅 Daily Duel turned off", "", "info"))
        if at:
            clock = _parse_clock(at)
            if not clock:
                return Reply(cards.notice("I couldn't read that time", "Try /daily 8pm or /daily 20:00", "bad"),
                             private=True)
            squad.daily["time"] = clock
            if clock <= datetime.now().strftime("%H:%M"):
                squad.daily["last_posted"] = datetime.now().date().isoformat()  # first one tomorrow
            store.save()
            return Reply(cards.notice(f"📅 Daily Duel set for {clock} every day",
                                      "One question, open for 30 minutes. Answer right to keep your 🔥 streak.", "gold"))
        err = await start_daily(squad, config.DAILY_NOW_SECONDS, topic)
        return Reply(cards.notice("Couldn't start the duel", esc(err), "bad"), private=True) if err else \
            Reply(cards.notice(f"📅 {uname} started today's Daily Duel!", "Schedule it with /daily 8pm", "gold"))
    if name == "profile":
        target = str(args.get("target_id") or uid)
        if args.get("target_name"):
            store.add_member(squad, target, args["target_name"])
        return Reply(cards.profile_card(squad, target))
    if name == "leaderboard":
        return Reply(cards.squad_board(squad))
    if name == "insights":
        asyncio.create_task(maybe_suggest(squad, force=True))
        return Reply(insights.overview(squad))
    if name == "radar":
        card, btns = radar_card(squad)
        return Reply(card, buttons=btns)
    if name == "plan":
        err = await create_plan(squad, topic, course, uid, uname, args.get("times", ""))
        return Reply(cards.notice("Couldn't make the poll", esc(err), "bad"), private=True) if err else Reply()
    if name == "focus":
        try:
            minutes = float(args.get("minutes") or 25)
        except ValueError:
            minutes = 25
        err = await start_focus(squad, uid, uname, minutes, topic)
        return Reply(cards.notice("Hold on", esc(err), "info"), private=True) if err else Reply()
    if name == "ask_cubbie":
        if not topic:
            return Reply(cards.notice("What topic?", "Try: /ask_cubbie caches", "info"), private=True)
        return Reply(cards.notice("📲 Asking your Cubbies", esc(ask_cubbies(squad, topic, course, uname)), "calm"))
    if name == "link":
        return Reply(cards.link_card(store.create_link(squad, uid, uname).key), private=True)
    if name in ("quiet", "watch"):
        squad.watching = name == "watch"
        store.save()
        return Reply(cards.notice("🤐 Okay, I'll only respond to commands here." if name == "quiet" else
                                  "👀 I'll suggest battles when you're prepping for something.",
                                  "I keep only the last few messages, in memory, and never store the chat." if
                                  name == "watch" else "/watch to undo.", "info"))
    return Reply(cards.help_card())


async def add_notes(squad: Squad, filename: str, data: bytes, course: str, by: str) -> Reply:
    try:
        body = notes.extract_text(filename, data)
    except notes.NotesError as exc:
        return Reply(cards.notice("Couldn't read that file", esc(exc), "bad"), private=True)
    insights.add_note(store, squad, filename, course, body, by)
    topic = course.upper() if course else filename.rsplit(".", 1)[0]
    btns = [Button("⚔️ Battle on these notes", token("start", squad.id, "boss", topic, course), "success"),
            Button("🕵️ Two Truths", token("start", squad.id, "lie", topic, course), "secondary")]
    return Reply(cards.notice(f"📎 Saved {filename}", f"{len(body.split())} words" +
                              (f" for {course.upper()}" if course else "") + ". Battles on these topics will use it.",
                              "good"), buttons=btns)


# chat watching ---------------------------------------------------------------------

async def on_chat_message(squad: Squad, user_id, name: str, body: str) -> None:
    """Called for every group message: Explain It answers first, then study-moment detection."""
    uid = str(user_id)
    store.add_member(squad, uid, name)
    _note_author(squad, uid)
    if _capture_explain(squad, uid, name, body):
        return
    if not squad.watching:   # /quiet: don't keep or read anything
        return
    buf = _recent.setdefault(squad.id, [])
    buf.append(f"{name}: {body[:300]}")
    del buf[:-20]
    if engine.is_panic(body):
        await _answer_panic(squad, name)
        return
    if not engine.can_nudge(squad, config.NUDGE_COOLDOWN_MINUTES) or busy(squad):
        return
    if not engine.looks_like_study_moment(body):
        return
    if time.time() - _moment_checks.get(squad.id, 0) < 60:   # at most one model call a minute per chat
        return
    _moment_checks[squad.id] = time.time()
    if await maybe_suggest(squad):
        return
    moment = await llm.detect_moment(buf)
    if not moment:
        return
    squad.last_nudge = time.time()
    store.save()
    await _send_offer(squad, moment["topic"], moment.get("course", ""), cards.offer(moment["topic"],
                                                                                    moment.get("course", "")))


async def _answer_panic(squad: Squad, name: str) -> None:
    """Someone said they're cooked: tell the whole chat which commands to use. The squad picks the topic."""
    if busy(squad) or time.time() - _panic_replies.get(squad.id, 0) < config.PANIC_COOLDOWN_MINUTES * 60:
        return
    _panic_replies[squad.id] = time.time()
    squad.last_nudge = time.time()
    store.save()
    await post(squad, cards.sos(name))


async def _send_offer(squad: Squad, topic: str, course: str, card: Card) -> None:
    btns = [Button("⚔️ Start battle", token("start", squad.id, "boss", topic, course), "success", 0),
            Button("🕵️ Two Truths", token("start", squad.id, "lie", topic, course), "primary", 0),
            Button("🎤 Explain It", token("explain", squad.id, topic, course), "primary", 0),
            Button("📲 Ask our Cubbies", token("ask", squad.id, topic, course), "secondary", 1),
            Button("Not now", token("dismiss", squad.id), "secondary", 1)]
    await post(squad, card, btns)


async def maybe_suggest(squad: Squad, force: bool = False) -> bool:
    """Post the best 'right moment' suggestion (from Cubbie snapshots and battle history), if there is one."""
    if squad.platform not in ADAPTERS or busy(squad) or not squad.watching:
        return False
    if not force and not engine.can_nudge(squad, config.NUDGE_COOLDOWN_MINUTES):
        return False
    found = insights.suggestions(squad)
    if not found:
        return False
    best = found[0]
    insights.mark_nudged(store, squad, best["key"])
    await _send_offer(squad, best["topic"], best["course"], cards.suggestion(best["text"]))
    return True
