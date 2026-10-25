"""Battle rules: scoring, boss and squad HP, streak crits, 50/50, final wagers, weak spots. No chat I/O here."""
from __future__ import annotations

import random
import re
import time
from collections import Counter

from .store import Game, Link, Question, Squad, Store

LETTERS = "ABCD"
SPEED_BONUS = [50, 30, 10]   # first, second, third correct answer on a question
CRIT_STREAK = 3              # a right answer on a 3+ streak is a critical hit
CRIT_BONUS = 50
VICTORY_HP = 30              # boss at or under this HP after the last question counts as beaten
BOSS_HIT = 35                # squad HP lost when everyone who answered got it wrong
IDLE_HIT = 10                # squad HP lost when nobody answered


def validate_questions(raw: list[dict], options: int | None = None) -> list[Question]:
    """Turn untrusted question dicts (from the LLM or a student's Cubbie) into Questions, or raise ValueError.
    `options` forces an exact option count; otherwise 2 to 4 are accepted."""
    if not isinstance(raw, list) or not raw:
        raise ValueError("questions must be a non-empty list")
    out = []
    for i, q in enumerate(raw[:10]):
        try:
            prompt = str(q["prompt"]).strip()[:400]
            opts = [str(o).strip()[:160] for o in q["options"]]
            answer = q["answer"]
            if isinstance(answer, str):
                answer = LETTERS.index(answer.strip().upper()[:1])
            answer = int(answer)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"question {i + 1} is malformed: {exc}") from None
        ok_count = len(opts) == options if options else 2 <= len(opts) <= 4
        if not prompt or not ok_count or not all(opts) or not 0 <= answer < len(opts):
            raise ValueError(f"question {i + 1} needs a prompt, {options or '2-4'} options and a valid answer")
        out.append(Question(prompt=prompt, options=opts, answer=answer,
                            explanation=str(q.get("explanation", "")).strip()[:300],
                            topic=str(q.get("topic", "")).strip()[:60]))
    return out


def question_damage(game: Game) -> float:
    return 100.0 / max(1, len(game.questions))


def is_final(game: Game, qi: int) -> bool:
    return qi == len(game.questions) - 1


def wants_wager(game: Game) -> bool:
    return game.mode in ("boss", "lie") and len(game.questions) >= 3


def record_answer(store: Store, game: Game, q_index: int, user_id, name: str, choice: int,
                  asked_at: float) -> str:
    """Returns 'locked', 'changed', 'removed' or 'closed'."""
    if game.status != "running" or q_index != game.current:
        return "closed"
    if choice in game.removed.get(str(q_index), []) or not 0 <= choice < len(game.questions[q_index].options):
        return "removed"
    uid = str(user_id)
    with store.lock:
        bucket = game.answers.setdefault(str(q_index), {})
        changed = uid in bucket
        bucket[uid] = [int(choice), round(time.time() - asked_at, 2)]
        game.names[uid] = name
    return "changed" if changed else "locked"


def use_fifty(store: Store, game: Game, q_index: int) -> list[int] | None:
    """Remove wrong options (two of four, one of three). Once per battle. Returns the removed indexes or None."""
    if game.fifty_used or game.status != "running" or q_index != game.current:
        return None
    q = game.questions[q_index]
    wrong = [i for i in range(len(q.options)) if i != q.answer]
    drop = random.sample(wrong, 2 if len(q.options) == 4 else 1)
    with store.lock:
        game.fifty_used = True
        game.removed[str(q_index)] = sorted(drop)
        bucket = game.answers.get(str(q_index), {})
        for uid in [u for u, (c, _) in bucket.items() if c in drop]:
            del bucket[uid]  # anyone who picked a removed option gets to answer again
    return sorted(drop)


def set_wager(store: Store, game: Game, user_id, name: str, fraction: float) -> bool:
    if game.status != "running" or not wants_wager(game):
        return False
    with store.lock:
        game.wagers[str(user_id)] = max(0.0, min(1.0, float(fraction)))
        game.names[str(user_id)] = name
    return True


def _bump(squad: Squad, uid: str, key: str, n: int = 1) -> None:
    squad.stats.setdefault(uid, {})
    squad.stats[uid][key] = squad.stats[uid].get(key, 0) + n


def close_question(store: Store, squad: Squad, game: Game) -> dict:
    """Score the current question, apply damage both ways, move on. Returns a summary for the reveal card."""
    with store.lock:
        qi = game.current
        q = game.questions[qi]
        bucket = game.answers.get(str(qi), {})
        correct = sorted((t, uid) for uid, (c, t) in bucket.items() if c == q.answer)
        right = {uid for _, uid in correct}
        wrong = [uid for uid in bucket if uid not in right]
        players = set(game.scores) | set(bucket)
        before = dict(game.scores)  # wagers are a share of the points held before the final question
        crits = []
        for rank, (_, uid) in enumerate(correct):
            game.streaks[uid] = game.streaks.get(uid, 0) + 1
            game.best_streaks[uid] = max(game.best_streaks.get(uid, 0), game.streaks[uid])
            pts = 100 + (SPEED_BONUS[rank] if rank < len(SPEED_BONUS) else 0)
            if game.streaks[uid] >= CRIT_STREAK:
                pts += CRIT_BONUS
                crits.append(uid)
            game.scores[uid] = game.scores.get(uid, 0) + pts
        for uid in players - right:
            game.streaks[uid] = 0
            game.scores.setdefault(uid, 0)
        for uid in bucket:
            _bump(squad, uid, "answered")
        for uid in right:
            _bump(squad, uid, "correct")

        wager_results = []
        if is_final(game, qi) and game.wagers:
            for uid, frac in game.wagers.items():
                stake = round(frac * before.get(uid, 0))
                if not stake:
                    continue
                delta = stake if uid in right else -stake
                game.scores[uid] = max(0, game.scores.get(uid, 0) + delta)
                wager_results.append((game.names.get(uid, uid), delta, frac))

        topic = q.topic or game.topic
        for uid in wrong:
            squad.weak.setdefault(uid, {})
            squad.weak[uid][topic] = squad.weak[uid].get(topic, 0) + 1

        damage = 0.0
        boss_hit = 0
        if game.mode != "daily":
            fraction = len(right) / len(bucket) if bucket else 0.0
            damage = question_damage(game) * fraction * (1.5 if crits else 1.0)
            game.hp = max(0.0, round(game.hp - damage, 1))
            if not bucket:
                boss_hit = IDLE_HIT
            elif wrong:
                boss_hit = round(BOSS_HIT * len(wrong) / len(bucket))
            game.squad_hp = max(0.0, game.squad_hp - boss_hit)

        game.current += 1
        last = game.current >= len(game.questions)
        if game.mode != "daily" and game.hp <= 0:
            game.outcome = "victory"
        elif game.mode != "daily" and game.squad_hp <= 0:
            game.outcome = "wiped"
        elif last:
            game.outcome = "victory" if game.mode != "daily" and game.hp <= VICTORY_HP else "survived"
        if game.outcome:
            game.status = "done"
            game.finished_at = time.time()
        store.save()
        return {
            "question": q,
            "index": qi,
            "correct": [game.names.get(uid, uid) for _, uid in correct],
            "correct_ids": [uid for _, uid in correct],
            "wrong": [game.names.get(uid, uid) for uid in wrong],
            "crits": [game.names.get(uid, uid) for uid in crits],
            "answered": len(bucket),
            "damage": round(damage, 1),
            "boss_hit": boss_hit,
            "hp": game.hp,
            "squad_hp": game.squad_hp,
            "wagers": wager_results,
            "done": game.status == "done",
            "outcome": game.outcome,
        }


def defeated(game: Game) -> bool:
    return game.outcome == "victory"


def leaderboard(game: Game) -> list[tuple[str, str, int]]:
    """[(user_id, name, points)] best first."""
    return sorted(((u, game.names.get(u, u), s) for u, s in game.scores.items()), key=lambda x: -x[2])


def group_weak_topics(game: Game, limit: int = 2) -> list[str]:
    """Topics the group missed most in this game."""
    misses = Counter()
    for qi, q in enumerate(game.questions):
        bucket = game.answers.get(str(qi), {})
        misses[q.topic or game.topic] += sum(1 for c, _ in bucket.values() if c != q.answer)
    return [t for t, n in misses.most_common(limit) if n > 0]


def perfect_players(game: Game) -> list[str]:
    asked = game.current
    out = []
    for uid in game.scores:
        hits = sum(1 for qi in range(asked)
                   if game.answers.get(str(qi), {}).get(uid, [None])[0] == game.questions[qi].answer)
        if asked >= 3 and hits == asked:
            out.append(uid)
    return out


def finish_game(store: Store, squad: Squad, game: Game) -> None:
    """Add points to the squad totals and drop a private result in each linked player's Cubbie inbox."""
    with store.lock:
        for uid, pts in game.scores.items():
            squad.totals[uid] = squad.totals.get(uid, 0) + pts
            _bump(squad, uid, "games")
        board = leaderboard(game)
        for link in store.links_for(squad.id):
            if link.user_id not in game.scores:
                continue
            missed = []
            for qi, q in enumerate(game.questions[:game.current]):
                ans = game.answers.get(str(qi), {}).get(link.user_id)
                if ans is None or ans[0] != q.answer:
                    missed.append({"prompt": q.prompt, "right": f"{LETTERS[q.answer]}) {q.options[q.answer]}",
                                   "explanation": q.explanation, "topic": q.topic or game.topic})
            rank = next((i + 1 for i, (u, _, _) in enumerate(board) if u == link.user_id), None)
            link.inbox.append({
                "type": "result", "game_id": game.id, "squad": squad.name, "topic": game.topic, "mode": game.mode,
                "boss_defeated": defeated(game), "points": game.scores[link.user_id], "rank": rank,
                "players": len(board), "missed": missed, "at": int(game.finished_at or time.time()),
            })
            link.inbox = link.inbox[-20:]
        store.save()


# chat watching -------------------------------------------------------------

STUDY_WORDS = re.compile(
    r"\b(midterm|final|exam|quiz|test|study|studying|cram|cooked|stressed|lost|confused|due|pset|homework)\b", re.I)
COURSE_CODE = re.compile(r"\b([A-Za-z]{2,4})\s?(\d{3})\b")
# "im cooked", "we're so cooked", "cooked fr", "gonna fail", "send help". Not "you cooked" / "i cooked pasta".
PANIC = re.compile(
    r"(?<!\bi )(?<!\bhe )(?<!\bshe )(?<!\bwe )(?<!\byou )(?<!\bthey )\bcooked\b"
    r"|\b(?:doomed|so screwed|so lost|so behind|send help|cramming|panicking|(?:gonna|going to|finna|about to) fail)\b",
    re.I)


def looks_like_study_moment(text: str) -> bool:
    return bool(STUDY_WORDS.search(text))


def is_panic(text: str) -> bool:
    return bool(PANIC.search(text))


def course_in(text: str) -> str:
    m = COURSE_CODE.search(text or "")
    return f"{m.group(1).upper()} {m.group(2)}" if m else ""


def can_nudge(squad: Squad, cooldown_minutes: float) -> bool:
    return squad.watching and time.time() - squad.last_nudge > cooldown_minutes * 60


def add_mention(store: Store, link: Link, squad: Squad, author: str, text: str) -> None:
    store.push_inbox(link, {"type": "mention", "squad": squad.name, "from": author,
                            "text": text[:300], "at": int(time.time())})
