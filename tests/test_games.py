"""Every game and feature end to end through the runner, with a fake chat app pressing buttons."""
import asyncio
import time
from datetime import date, datetime, timedelta

from conftest import FakeAdapter

from cramberry import config, insights, runner
from cramberry.store import store


def press(adapter_sent_buttons, label, uid, name):
    tok = next(b.token for b in adapter_sent_buttons if b.label.startswith(label))
    return runner.press(tok, uid, name)


async def wait_for(cond, timeout=30):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("timed out")


def autoplayer(right_uid="a", wrong_uid="b", use_fifty=True, wager="🔥 ALL IN"):
    """A always answers right, B always wrong. A uses the 50/50 once and goes all in on the final."""
    state = {"fifty": use_fifty}

    async def on_send(adapter, card, buttons):
        if card.title.startswith("💰 Final strike"):
            await press(buttons, wager, right_uid, "Alice")
            return
        letters = [b for b in buttons if len(b.label) == 1]
        if not letters:
            return
        game = next(g for g in store.games.values() if g.status == "running" and g.squad_id.startswith(adapter.platform))
        q = game.questions[game.current]
        if state["fifty"]:
            state["fifty"] = False
            await press(buttons, "🎲", right_uid, "Alice")
        right = q.answer
        wrong = next(i for i in range(len(q.options)) if i != right and i not in game.removed.get(str(game.current), []))
        await runner.press(next(b.token for b in letters if b.label == "ABCD"[right]), right_uid, "Alice")
        await runner.press(next(b.token for b in letters if b.label == "ABCD"[wrong]), wrong_uid, "Bob")
    return on_send


def test_boss_battle_with_power_ups_wager_and_awards():
    adapter = FakeAdapter("gboss", autoplayer())
    runner.register(adapter)
    squad = store.squad("gboss", "c1", "boss squad")

    async def go():
        reply = await runner.command(squad, "battle", "a", "Alice", {"topic": "caches"})
        assert "summoned a boss" in reply.card.title
        again = await runner.command(squad, "battle", "b", "Bob", {"topic": "caches"})
        assert again.private and "already" in again.card.body
        await wait_for(lambda: any(t.startswith(("🏆", "😤", "💀")) for t in adapter.titles()))

    asyncio.run(go())
    titles = adapter.titles()
    assert titles[0].startswith("⚔️ The Caches Boss has appeared")
    assert any(t.startswith("🎲 Alice used the 50/50") for t in titles)
    assert any(t.startswith("💰 Final strike") for t in titles)
    assert any("FINAL STRIKE" in t for t in titles)
    final = adapter.sent[-1]
    assert "Leaderboard" in final["card"].fields[0][0] and "Alice" in final["card"].fields[0][1]
    assert [b.label for b in final["buttons"]][0].startswith("🔁 Rematch")
    assert squad.xp["a"] > squad.xp.get("b", 0) > 0
    assert squad.stats["a"]["correct"] == 5 and squad.stats["b"]["answered"] == 5
    reveal = next(s for s in adapter.sent if s["card"].title.startswith("✅ Q3"))
    assert "CRIT" in reveal["card"].body and "hits back" in reveal["card"].body


def test_two_truths_and_a_lie():
    adapter = FakeAdapter("glie", autoplayer(use_fifty=False, wager="🛡️"))
    runner.register(adapter)
    squad = store.squad("glie", "c1", "lie squad")

    async def go():
        reply = await runner.command(squad, "lie", "a", "Alice", {"topic": "caches"})
        assert "Two Truths" in reply.card.title
        await wait_for(lambda: any(t.startswith(("🏆", "😤", "💀")) for t in adapter.titles()))

    asyncio.run(go())
    q = next(s for s in adapter.sent if s["card"].title.startswith("🕵️ Round 1"))
    assert [b.label for b in q["buttons"] if len(b.label) == 1] == ["A", "B", "C"]
    assert "Which one is the lie?" in q["card"].body
    assert "liedetector" in squad.badges["a"]


def test_explain_it_round_pass_and_open_floor():
    adapter = FakeAdapter("gexp")
    runner.register(adapter)
    squad = store.squad("gexp", "c1", "explain squad")

    async def go():
        err = await runner.start_explain(squad, "caches", "", "a", "Alice")
        assert not err
        await wait_for(lambda: adapter.find("🎤 Round 1"))
        await runner.on_chat_message(squad, "b", "Bob", "this is not my turn but here is a long message")
        await runner.on_chat_message(squad, "a", "Alice", "Stores go to the cache, a dirty bit marks changed blocks, "
                                                          "memory is written on eviction.")
        await wait_for(lambda: adapter.find("🧠 Alice"))
        await wait_for(lambda: adapter.find("🎤 Round 2"))
        target = adapter.find("🎤 Round 2")[0]["mentions"][0]
        await runner.on_chat_message(squad, target[0], target[1], "pass")
        await wait_for(lambda: adapter.find("🙋 Open floor"))
        await runner.on_chat_message(squad, "b", "Bob", "Each address maps to one set and the block can go in "
                                                        "either of 2 ways, so fewer conflict misses.")
        await wait_for(lambda: adapter.find("🎤 Explain It · final"))

    asyncio.run(go())
    alice = adapter.find("🧠 Alice")[0]["card"]
    assert alice.title.startswith("🧠 Alice: 10/10") and "professor" in squad.badges["a"]
    bob = adapter.find("🧠 Bob")[0]["card"]
    assert "(open floor)" in bob.title
    assert squad.stats["a"]["explains"] == 1


def test_daily_duel_now_and_scheduled():
    adapter = FakeAdapter("gday", autoplayer(use_fifty=False))
    runner.register(adapter)
    squad = store.squad("gday", "c1", "daily squad")
    squad.weak = {"a": {"associativity": 2}}

    async def go():
        reply = await runner.command(squad, "daily", "a", "Alice", {})
        assert "Daily Duel" in reply.card.title
        await wait_for(lambda: adapter.find("📅 Daily Duel results"))
        set_reply = await runner.command(squad, "daily", "a", "Alice", {"at": "8pm"})
        assert "20:00" in set_reply.card.title
        squad.daily["last_posted"] = ""
        await runner._tick(datetime.now().replace(hour=20, minute=1))
        await wait_for(lambda: len(adapter.find("📅 Daily Duel results")) == 2)
        off = await runner.command(squad, "daily", "a", "Alice", {"at": "off"})
        assert "off" in off.card.title

    asyncio.run(go())
    res = adapter.find("📅 Daily Duel results")[0]["card"]
    assert "✅ Alice" in res.fields[0][1] and "❌ Bob" in res.fields[0][1]
    assert squad.user_daily["a"]["streak"] == 1 and squad.daily["streak"] == 1
    assert "time" not in squad.daily


def test_focus_plan_radar_and_reminders():
    adapter = FakeAdapter("gplan")
    runner.register(adapter)
    squad = store.squad("gplan", "c1", "plan squad")
    store.add_member(squad, "a", "Alice")
    link = store.create_link(squad, "b", "Bob")
    soon = (date.today() + timedelta(days=2)).isoformat()
    snap = {"courses": [{"code": "SES 141", "name": "Chemistry", "topics": ["chemical energy"],
                         "upcoming": [{"title": "Exam 1", "kind": "exam", "due": soon, "topic": "chemical energy"}]}]}
    insights.save_snapshot(store, squad, link, insights.clean_snapshot(snap))

    async def go():
        assert not await runner.start_focus(squad, "a", "Alice", 25, "stoichiometry", seconds=0.5)
        assert "already running" in await runner.start_focus(squad, "b", "Bob", 25)
        ack = await press(adapter.sent[-1]["buttons"], "🍅 Join", "b", "Bob")
        assert "You're in" in ack
        await wait_for(lambda: adapter.find("⏰ Break time"))

        reply = await runner.command(squad, "plan", "a", "Alice", {"topic": "chemical energy", "times": ""})
        assert reply.card is None
        poll = adapter.find("📆 When should we study")[0]
        assert "Only Alice" in await press(poll["buttons"], "📌", "b", "Bob")
        assert "Nobody has voted" in await press(poll["buttons"], "📌", "a", "Alice")
        assert "You're in" in await press(poll["buttons"], poll["buttons"][0].label[:5], "b", "Bob")
        assert "Locked" in await press(poll["buttons"], "📌", "a", "Alice")

        radar = await runner.command(squad, "radar", "a", "Alice")
        assert "SES 141" in radar.card.body and radar.card.body.count("Exam 1") == 1
        assert radar.buttons[0].label.startswith("⚔️ Battle")

        plan = squad.plans[-1]
        squad.radar["last"] = ""
        await runner._tick(datetime.now().replace(hour=9, minute=5))
        await runner._tick(datetime.fromtimestamp(plan["chosen_ts"] - 600))

    asyncio.run(go())
    brk = adapter.find("⏰ Break time")[0]
    assert {m[0] for m in brk["mentions"]} == {"a", "b"} and squad.stats["b"]["focus"] == 1
    assert any(i["type"] == "session" for i in link.inbox)
    assert adapter.find("📡 Deadline radar") and adapter.find("⏰ Study session in 30 min")


def test_offer_buttons_insights_profile_help_notes():
    adapter = FakeAdapter("gmisc")
    runner.register(adapter)
    squad = store.squad("gmisc", "c1", "misc squad")

    async def go():
        await runner.on_chat_message(squad, "a", "Alice", "bro the cache midterm is thursday, gotta study")
        offer = adapter.find("👀 Study moment")[0]
        assert [b.label for b in offer["buttons"]][:3] == ["⚔️ Start battle", "🕵️ Two Truths", "🎤 Explain It"]
        assert "No worries" in await press(offer["buttons"], "Not now", "a", "Alice")
        await runner.on_chat_message(squad, "a", "Alice", "seriously need to study for the exam")
        assert len(adapter.find("👀 Study moment")) == 1  # cooldown
        await runner.command(squad, "quiet", "a", "Alice")
        await runner.on_chat_message(squad, "a", "Alice", "exam exam exam")
        assert not runner._recent[squad.id][-1].endswith("exam exam exam")  # /quiet keeps nothing
        for name in ("help", "profile", "leaderboard", "insights", "link"):
            reply = await runner.command(squad, name, "a", "Alice")
            assert reply.card and reply.card.title
        assert (await runner.command(squad, "link", "a", "Alice")).private
        notes = await runner.add_notes(squad, "lec.md", b"# Caches\n\nDirect mapped and set associative caches...",
                                       "cse 230", "Alice")
        assert notes.card.title.startswith("📎 Saved") and notes.buttons

    asyncio.run(go())


def test_course_aware_topics():
    squad = store.squad("gcourse", "c1", "course squad")
    link = store.create_link(squad, "a", "Alice")
    snap = {"courses": [{"code": "CSE 230", "name": "Computer Organization and Assembly", "topics": ["caches", "TLB"]}]}
    insights.save_snapshot(store, squad, link, insights.clean_snapshot(snap))
    topic, course, ctx = insights.resolve(squad, "CSE230", "")
    assert course == "CSE 230" and topic.startswith("CSE 230 Computer Organization") and "caches" in topic
    assert "Computer Organization" in ctx and "this week: caches, TLB" in ctx
    topic, course, ctx = insights.resolve(squad, "virtual memory", "cse 230")
    assert topic == "virtual memory" and ctx
    assert insights.resolve(squad, "photosynthesis", "")[2] == ""


def test_im_cooked_rallies_the_whole_squad(monkeypatch):
    adapter = FakeAdapter("gcooked")
    runner.register(adapter)
    squad = store.squad("gcooked", "c1", "cooked squad")

    async def never(messages):
        raise AssertionError("the cooked reply must not guess a topic")

    async def go():
        monkeypatch.setattr(runner.llm, "detect_moment", never)
        await runner.on_chat_message(squad, "a", "Alice", "bro im so cooked on caches")
        sos = adapter.find("🆘 Alice is cooked")[0]
        steps = sos["card"].fields[0][1]
        assert "`/battle`" in steps and "`/radar`" in steps and "caches" not in steps  # the squad types the topic
        assert not sos["buttons"]
        await runner.on_chat_message(squad, "b", "Bob", "cooked fr")
        assert len(adapter.find("🆘")) == 1  # one reply per cooldown, not one per message
        monkeypatch.setattr(runner.config, "PANIC_COOLDOWN_MINUTES", 0)
        await runner.on_chat_message(squad, "b", "Bob", "you cooked on that pset")  # a compliment, not panic
        assert len(adapter.find("🆘")) == 1
        await runner.on_chat_message(squad, "b", "Bob", "we're doomed")
        assert adapter.find("🆘 Bob is cooked")
        await runner.command(squad, "quiet", "a", "Alice")
        await runner.on_chat_message(squad, "a", "Alice", "im cooked")  # /quiet: stays out of the chat
        assert len(adapter.find("🆘")) == 2

    asyncio.run(go())
