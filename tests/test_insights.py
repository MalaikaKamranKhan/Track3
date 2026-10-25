"""Course snapshots, right-moment suggestions, Cubbie requests and notes, including the script over real HTTP."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from datetime import date, timedelta
from pathlib import Path

import uvicorn  # noqa: E402
from conftest import FakeAdapter  # noqa: E402

from cramberry import insights, notes, runner  # noqa: E402
from cramberry.api import app  # noqa: E402
from cramberry.store import store  # noqa: E402

SCRIPT = Path(__file__).resolve().parent.parent / "cubbie-skill" / "squad-link" / "scripts" / "squad.py"
PORT = 8766


def RecordingAdapter():
    return FakeAdapter("insighttest")


def offers(adapter):
    return [x for x in adapter.sent if x["card"].title.startswith("💡")]


def snapshot(submitted=True, exam_in_days=None):
    upcoming = []
    if exam_in_days is not None:
        upcoming.append({"title": "Midterm 2", "kind": "exam",
                         "due": (date.today() + timedelta(days=exam_in_days)).isoformat(), "topic": "caches"})
    return {"courses": [{"code": "cse 230", "name": "Computer Org", "topics": ["caches"],
                         "upcoming": upcoming,
                         "submitted": [{"title": "PSET 4", "topic": "caches"}] if submitted else []}]}


def test_clean_snapshot_keeps_only_safe_fields():
    raw = snapshot(exam_in_days=2)
    raw["courses"][0]["grade"] = "A-"
    clean = insights.clean_snapshot(raw)
    course = clean["courses"][0]
    assert course["code"] == "CSE 230" and "grade" not in course
    for bad in ({}, {"courses": [{"name": "no code"}]},
                {"courses": [{"code": "X 1", "upcoming": [{"title": "t", "due": "next week"}]}]}):
        try:
            insights.clean_snapshot(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad}")


def test_suggestions_from_snapshots_and_weak_spots():
    squad = store.squad("insighttest", "s1", "suggest squad")
    a, b = store.create_link(squad, "a", "Malaika"), store.create_link(squad, "b", "Sashi")
    insights.save_snapshot(store, squad, a, insights.clean_snapshot(snapshot(exam_in_days=1)))
    insights.save_snapshot(store, squad, b, insights.clean_snapshot(snapshot(submitted=False, exam_in_days=1)))
    found = insights.suggestions(squad)
    assert found[0]["key"].startswith("exam:") and "2 of you have the CSE 230 Midterm 2 tomorrow" in found[0]["text"]
    assert not any(s["key"].startswith("done:") for s in found)  # Sashi hasn't submitted PSET 4

    insights.save_snapshot(store, squad, b, insights.clean_snapshot(snapshot(exam_in_days=None)))
    keys = [s["key"] for s in insights.suggestions(squad)]
    assert any(k.startswith("done:CSE 230") for k in keys)
    squad.weak = {"a": {"associativity": 2}, "b": {"associativity": 1}}
    assert any(s["key"].startswith("weak:associativity") for s in insights.suggestions(squad))
    from cramberry.cards import plain
    text = plain(insights.overview(squad))
    assert "CSE 230" in text and "weak spots" in text


def test_maybe_suggest_posts_once():
    adapter = RecordingAdapter()
    runner.register(adapter)
    squad = store.squad("insighttest", "s2", "nudge squad")
    a, b = store.create_link(squad, "a", "Malaika"), store.create_link(squad, "b", "Sashi")
    for link in (a, b):
        insights.save_snapshot(store, squad, link, insights.clean_snapshot(snapshot()))
    assert asyncio.run(runner.maybe_suggest(squad, force=True))
    first = offers(adapter)[0]
    kind, data, _ = runner._actions[first["buttons"][0].token]
    assert kind == "start" and data[2:] == ("caches", "CSE 230")
    assert "Both of you submitted" in first["card"].body
    assert not asyncio.run(runner.maybe_suggest(squad, force=True))  # never the same suggestion twice
    squad.watching = False
    squad.nudged.clear()
    assert not asyncio.run(runner.maybe_suggest(squad, force=True))  # /quiet wins


def test_notes_pick_matching_material():
    squad = store.squad("insighttest", "s3", "notes squad")
    insights.add_note(store, squad, "lec12-caches.pdf", "cse 230", "Caches: direct mapped, set associative...", "M")
    insights.add_note(store, squad, "lec3-induction.txt", "MAT 243", "Proof by induction: base case...", "M")
    assert "lec12-caches" in insights.material_for(squad, "caches", "CSE 230")
    assert "induction" in insights.material_for(squad, "induction proofs")
    assert insights.material_for(squad, "photosynthesis") == ""
    assert "base case" in notes.extract_text("n.md", b"# Induction\n\nProof by induction: base case and step...")
    for name, data in (("x.docx", b"whatever" * 20), ("short.txt", b"hi")):
        try:
            notes.extract_text(name, data)
        except notes.NotesError:
            continue
        raise AssertionError(name)


def run_script(key, *args, cwd=None):
    env = {**os.environ, "SQUAD_API_KEY": key}
    return subprocess.run([sys.executable, "-I", str(SCRIPT), "--server", f"http://127.0.0.1:{PORT}", *args],
                          capture_output=True, text=True, env=env, cwd=cwd, timeout=60)


def test_cubbie_checkin_requests_and_snapshot_over_http():
    adapter = RecordingAdapter()
    runner.register(adapter)
    squad = store.squad("insighttest", "s4", "http squad")
    a, b = store.create_link(squad, "a", "Malaika"), store.create_link(squad, "b", "Sashi")

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_until_complete, args=(server.serve(),), daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.1)
    work = tempfile.mkdtemp()

    assert "NOTHING NEW" in run_script(a.key, "checkin").stdout

    # squad asks the Cubbies from Discord; both mailboxes get the request
    msg = runner.ask_cubbies(squad, "caches", "CSE 230", "Sashi")
    assert msg.startswith("Asked 2 linked Cubbies")
    out = run_script(a.key, "checkin").stdout
    assert "REQUEST id=" in out and 'topic="caches"' in out and "from=Sashi" in out, out
    rid = out.split("REQUEST id=")[1].split()[0]

    # Malaika's Cubbie answers it; the request disappears for Sashi's Cubbie too
    qs = {"questions": [{"prompt": "Q?", "options": ["a", "b", "c", "d"], "answer": "A"}] * 3}
    Path(work, "questions.json").write_text(json.dumps(qs))
    posted = run_script(a.key, "challenge", "--topic", "caches", "--course", "CSE 230",
                        "--questions-file", "questions.json", "--request-id", rid, cwd=work)
    assert posted.returncode == 0, posted
    assert "REQUEST" not in run_script(b.key, "checkin").stdout
    store.games[squad.game_ids[-1]].status = "done"

    # decline path
    runner.ask_cubbies(squad, "TLB", "CSE 230", "Malaika")
    rid2 = run_script(b.key, "checkin", "--keep").stdout.split("REQUEST id=")[1].split()[0]
    assert run_script(b.key, "decline", "--request-id", rid2).returncode == 0
    assert "REQUEST" not in run_script(b.key, "checkin").stdout

    # both Cubbies drop off snapshots -> the bot posts a right-moment suggestion in the group
    Path(work, "snap.json").write_text(json.dumps(snapshot()))
    assert "SHARED course snapshot" in run_script(a.key, "checkin", "--snapshot-file", "snap.json", cwd=work).stdout
    run_script(b.key, "checkin", "--snapshot-file", "snap.json", cwd=work)
    deadline = time.time() + 5
    while not offers(adapter) and time.time() < deadline:
        time.sleep(0.2)
    assert offers(adapter) and "Both of you submitted CSE 230 PSET 4" in offers(adapter)[-1]["card"].body

    Path(work, "bad.json").write_text(json.dumps({"courses": [{"name": "no code"}]}))
    assert run_script(a.key, "checkin", "--snapshot-file", "bad.json", cwd=work).returncode == 2

    server.should_exit = True
    thread.join(timeout=5)
