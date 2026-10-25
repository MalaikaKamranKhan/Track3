"""Pure rules: scoring, crits, the boss hitting back, 50/50, wagers, progress, time parsing, card rendering."""
import time
from datetime import date, datetime, timedelta

from squadbot import cards, engine, planner, progress
from squadbot.store import store


def make_game(squad, n=4, options=4, mode="boss"):
    qs = engine.validate_questions([{"prompt": f"Q{i}", "options": [f"o{j}" for j in range(options)], "answer": 1,
                                     "explanation": "e", "topic": f"t{i}"} for i in range(n)])
    return store.new_game(squad, "caches", qs, mode=mode)


def answer_all(game, picks):
    for uid, choice in picks.items():
        assert engine.record_answer(store, game, game.current, uid, uid.upper(), choice, time.time()) in ("locked", "changed")


def test_validate_questions():
    good = [{"prompt": "2+2?", "options": ["3", "4", "5", "6"], "answer": "B"}]
    assert engine.validate_questions(good)[0].answer == 1
    lie = [{"prompt": "lie?", "options": ["a", "b", "c"], "answer": 2}]
    assert engine.validate_questions(lie, options=3)[0].answer == 2
    for bad, opts in (([], None), ([{"prompt": "x", "options": ["a"], "answer": 0}], None),
                      ([{"prompt": "x", "options": ["a", "b", "c", "d"], "answer": 9}], None), (good, 3)):
        try:
            engine.validate_questions(bad, options=opts)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_crits_boss_hits_back_and_victory():
    squad = store.squad("rules", "1", "rules squad")
    game = make_game(squad, n=4)
    for qi in range(4):
        answer_all(game, {"a": 1, "b": 0})
        s = engine.close_question(store, squad, game)
        assert s["boss_hit"] == round(engine.BOSS_HIT / 2)
        if qi == 2:
            assert s["crits"] == ["A"]  # third right answer in a row
    assert game.status == "done" and game.scores["a"] > game.scores["b"] == 0
    assert game.squad_hp == 100 - 4 * round(engine.BOSS_HIT / 2)
    assert game.outcome == "survived"  # half the squad right every time leaves the boss above 30%


def test_squad_wipe_and_idle_hits():
    squad = store.squad("rules", "2", "wipe squad")
    game = make_game(squad, n=5)
    s = engine.close_question(store, squad, game)
    assert s["boss_hit"] == engine.IDLE_HIT and game.squad_hp == 90
    for _ in range(3):
        answer_all(game, {"a": 0})
        s = engine.close_question(store, squad, game)
    assert s["outcome"] == "wiped" and game.status == "done"


def test_fifty_and_wager():
    squad = store.squad("rules", "3", "wager squad")
    game = make_game(squad, n=3)
    answer_all(game, {"a": 0})
    dropped = engine.use_fifty(store, game, 0)
    assert len(dropped) == 2 and 1 not in dropped
    assert engine.use_fifty(store, game, 0) is None
    assert engine.record_answer(store, game, 0, "b", "B", dropped[0], time.time()) == "removed"
    if 0 in dropped:
        assert "a" not in game.answers["0"]  # picked a removed option, so they can answer again
    for _ in range(2):
        answer_all(game, {"a": 1})
        engine.close_question(store, squad, game)
    before = game.scores["a"]
    assert engine.set_wager(store, game, "a", "A", 1.0)
    answer_all(game, {"a": 1})
    s = engine.close_question(store, squad, game)
    assert s["wagers"] == [("A", before, 1.0)]
    assert game.scores["a"] == before * 2 + 100 + 50 + 50  # stake + base + speed + crit


def test_progress_levels_badges_and_daily_streaks():
    squad = store.squad("rules", "4", "progress squad")
    assert progress.level_for(0)[0] == 1 and progress.level_for(150)[0] == 2
    a = progress.award(store, squad, "a", 120, ["slayer", "slayer", "nope"])
    assert a["level_up"] and a["badges"] == ["slayer"]
    assert progress.award(store, squad, "a", 10, ["slayer"])["badges"] == []
    d0 = date(2026, 10, 20)
    for i in range(3):
        out = progress.record_daily(store, squad, d0 + timedelta(days=i), ["a"], ["a", "b"])
    assert out["a"] == 3 and out["b"] == 0 and out["_squad"] == 3
    out = progress.record_daily(store, squad, d0 + timedelta(days=5), ["a"], ["a"])
    assert out["a"] == 1
    p = progress.profile(squad, "a")
    assert p["level"] == 2 and p["badges"] == ["slayer"] and p["daily"] == 1


def test_planner_parsing_and_reminders():
    now = datetime(2026, 10, 24, 18, 0)  # a Saturday
    assert planner.parse_slot("tue 7pm", now) == datetime(2026, 10, 27, 19, 0)
    assert planner.parse_slot("tomorrow 6:30pm", now) == datetime(2026, 10, 25, 18, 30)
    assert planner.parse_slot("tonight 8", now) == datetime(2026, 10, 24, 20, 0)
    assert planner.parse_slot("10/28 21:00", now) == datetime(2026, 10, 28, 21, 0)
    assert planner.parse_slot("whenever", now) is None
    assert planner.label(datetime(2026, 10, 25, 18, 30), now) == "Tomorrow 6:30 PM"
    assert [d.hour for d in planner.default_slots(now)] == [19, 19, 19]
    squad = store.squad("rules", "5", "plan squad")
    plan, err = planner.create(store, squad, "caches", "CSE 230", "a", "A", "tue 7pm, wed 6pm", now)
    assert not err and len(plan["slots"]) == 2
    _, err = planner.create(store, squad, "x", "", "a", "A", "someday", now)
    assert "couldn't read" in err
    assert planner.toggle_vote(store, squad, plan, 1, "b", "B")
    assert not planner.toggle_vote(store, squad, plan, 1, "b", "B")
    planner.toggle_vote(store, squad, plan, 1, "b", "B")
    planner.lock(store, squad, plan)
    assert plan["chosen"] == 1 and "locked" in planner.card(plan, squad).title.lower()
    ts = plan["chosen_ts"]
    assert planner.due_reminders(squad, ts - 3600) == []
    assert planner.due_reminders(squad, ts - 600)[0][1] == "soon"
    plan["reminded"].append("soon")
    assert planner.due_reminders(squad, ts + 60)[0][1] == "start"


def test_card_text_helpers():
    card = cards.Card("T <1>", f"**bold** and {cards.esc('a*b_c <x>')}", "info", [("F", "`code`", True)], "foot")
    assert cards.esc("a*b_c") == r"a\*b\_c"
    assert cards.plain(card).startswith("T <1>") and "bold and a*b_c <x>" in cards.plain(card)
    assert cards.boss_name("CPU caches") == "The CPU Caches Boss"
    assert cards.bar(60).startswith("🟥" * 6)
