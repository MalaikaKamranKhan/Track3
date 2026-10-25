"""The Cubbie script -> API -> group battle -> private recap loop, with a real HTTP server on localhost."""
import asyncio
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn  # noqa: E402
from conftest import FakeAdapter  # noqa: E402

from squadbot import runner  # noqa: E402
from squadbot.api import app  # noqa: E402
from squadbot.store import store  # noqa: E402

SCRIPT = Path(__file__).resolve().parent.parent / "cubbie-skill" / "squad-link" / "scripts" / "squad.py"
PORT = 8765


def AutoPlayAdapter():
    """A group chat where two friends answer every question; Malaika misses the first one."""
    async def on_send(adapter, card, buttons):
        letters = [b for b in buttons if len(b.label) == 1]
        if not letters:
            return
        game = next(g for g in store.games.values() if g.status == "running" and g.squad_id.startswith("bridgetest"))
        qi, right = game.current, game.questions[game.current].answer
        tok = {b.label: b.token for b in letters}
        await runner.press(tok["ABCD"[right if qi else (right + 1) % 4]], "u1", "Malaika")
        await runner.press(tok["ABCD"[right]], "u2", "Dhanush")
    return FakeAdapter("bridgetest", on_send)


def run_script(key, *args, cwd=None):
    env = {**os.environ, "SQUAD_API_KEY": key}
    return subprocess.run([sys.executable, "-I", str(SCRIPT), "--server", f"http://127.0.0.1:{PORT}", *args],
                          capture_output=True, text=True, env=env, cwd=cwd, timeout=60)


def test_cubbie_bridge_end_to_end():
    adapter = AutoPlayAdapter()
    runner.register(adapter)
    squad = store.squad("bridgetest", "g1", "CSE 230 grind")
    store.add_member(squad, "u1", "Malaika")
    link = store.create_link(squad, "u1", "Malaika")

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_until_complete, args=(server.serve(),), daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.1)

    me = run_script(link.key, "me")
    assert me.returncode == 0 and "Linked as Malaika to CSE 230 grind" in me.stdout, me

    assert run_script("sq_wrong", "me").returncode == 5
    assert subprocess.run([sys.executable, "-I", str(SCRIPT), "me"], capture_output=True,
                          env={k: v for k, v in os.environ.items() if k != "SQUAD_API_KEY"}).returncode == 3

    work = tempfile.mkdtemp()
    qs = {"questions": [{"prompt": f"Q{i}: which is right?", "options": ["w", "x", "y", "z"], "answer": "C",
                         "explanation": f"because {i}", "topic": "set index"} for i in range(3)]}
    Path(work, "questions.json").write_text(json.dumps(qs))
    bad = Path(work, "bad.json")
    bad.write_text(json.dumps({"questions": [{"prompt": "x", "options": ["a"], "answer": "A"}]}))
    assert run_script(link.key, "challenge", "--topic", "caches", "--questions-file", str(bad)).returncode == 2

    posted = run_script(link.key, "challenge", "--topic", "caches", "--questions-file", "questions.json", cwd=work)
    assert posted.returncode == 0 and "Posted a 3-question caches boss battle" in posted.stdout, posted
    assert "Malaika's Cubbie" in adapter.sent[0]["card"].body

    busy = run_script(link.key, "challenge", "--topic", "caches", "--material-file", "questions.json", cwd=work)
    assert busy.returncode == 6, busy

    deadline = time.time() + 60
    while store.active_game(squad.id) and time.time() < deadline:
        time.sleep(0.5)
    time.sleep(1)

    recap = run_script(link.key, "results")
    assert recap.returncode == 0, recap
    assert "RESULT" in recap.stdout and "#2 of 2" in recap.stdout, recap.stdout
    assert recap.stdout.count("MISSED") == 1 and "because 0" in recap.stdout
    assert "WEAK TOPICS so far: set index" in recap.stdout
    assert "NOTHING NEW" in run_script(link.key, "results").stdout  # marked read

    # a locked study session reaches the Cubbie as a SESSION line
    from squadbot import planner
    plan, _ = planner.create(store, squad, "caches", "CSE 230", "u2", "Dhanush", "tomorrow 7pm")
    planner.toggle_vote(store, squad, plan, 0, "u1", "Malaika")
    planner.toggle_vote(store, squad, plan, 0, "u2", "Dhanush")
    tok = runner.token("plan_lock", squad.id, plan["id"])
    assert "Locked" in asyncio.run(runner.press(tok, "u2", "Dhanush"))
    out = run_script(link.key, "checkin").stdout
    assert "SESSION start=" in out and 'topic="caches"' in out and "with=Dhanush" in out, out

    server.should_exit = True
    thread.join(timeout=5)
