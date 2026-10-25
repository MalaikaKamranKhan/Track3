"""HTTPS API used by the squad-link Cubbie Skill. Every call carries the student's private key as a Bearer token."""
from __future__ import annotations

import asyncio

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from . import config, insights, runner
from .store import Link, store

app = FastAPI(title=f"{config.BOT_NAME} squad server", docs_url=None, redoc_url=None)


def current_link(authorization: str = Header(default="")) -> Link:
    key = authorization.removeprefix("Bearer ").strip()
    link = store.links.get(key)
    if not link:
        raise HTTPException(401, "Unknown squad key. Run /link in your group chat to get a new one.")
    return link


class Challenge(BaseModel):
    topic: str = Field(min_length=1, max_length=80)
    questions: list[dict] | None = None      # written by the student's Cubbie from their course material
    material: str = Field(default="", max_length=20000)  # or: raw notes for the server to turn into questions
    course: str = Field(default="", max_length=20)
    request_id: str = Field(default="", max_length=20)   # set when answering a squad's "ask our Cubbies" request


class CheckIn(BaseModel):
    snapshot: dict | None = None   # what the student's Cubbie read from Canvas; see insights.clean_snapshot
    keep: bool = False             # don't mark results as read


@app.get("/health")
def health():
    return {"ok": True, "bots": sorted(runner.ADAPTERS)}


@app.get("/api/me")
def me(link: Link = Depends(current_link)):
    squad = store.squads[link.squad_id]
    return {"player": link.name, "squad": squad.name, "platform": squad.platform,
            "members": len(squad.members), "battle_running": bool(store.active_game(squad.id))}


@app.post("/api/challenge")
async def challenge(body: Challenge, link: Link = Depends(current_link)):
    squad = store.squads[link.squad_id]
    game, err = await runner.start_battle(squad, body.topic, questions=body.questions, material=body.material,
                                          source=f"cubbie:{link.name}", course=body.course)
    if not game:
        code = 409 if "already" in err else 503 if "isn't running" in err else 400
        raise HTTPException(code, err)
    if body.request_id:
        insights.close_request(store, squad.id, body.request_id)
    return {"ok": True, "game_id": game.id, "squad": squad.name, "platform": squad.platform,
            "questions": len(game.questions)}


@app.post("/api/checkin")
async def checkin(body: CheckIn, link: Link = Depends(current_link)):
    """Cubbie's scheduled visit: drop off a course snapshot, pick up requests, results and mentions."""
    squad = store.squads[link.squad_id]
    shared = False
    if body.snapshot is not None:
        try:
            snap = insights.clean_snapshot(body.snapshot)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        insights.save_snapshot(store, squad, link, snap)
        shared = True
        asyncio.create_task(runner.maybe_suggest(squad, force=True))  # the squad may have just hit a "right moment"
    items = store.take_inbox(link, keep=body.keep)
    weak = squad.weak.get(link.user_id, {})
    return {"player": link.name, "squad": squad.name, "snapshot_shared": shared,
            "requests": link.requests, "inbox": items,
            "weak_topics": [t for t, _ in sorted(weak.items(), key=lambda kv: -kv[1])[:3]],
            "total_points": squad.totals.get(link.user_id, 0)}


@app.post("/api/requests/{request_id}/decline")
def decline(request_id: str, link: Link = Depends(current_link)):
    insights.decline_request(store, link, request_id)
    return {"ok": True}


@app.get("/api/results")
def results(keep: bool = False, link: Link = Depends(current_link)):
    squad = store.squads[link.squad_id]
    weak = squad.weak.get(link.user_id, {})
    items = store.take_inbox(link, keep=keep)
    return {"player": link.name, "squad": squad.name,
            "weak_topics": [t for t, _ in sorted(weak.items(), key=lambda kv: -kv[1])[:3]],
            "total_points": squad.totals.get(link.user_id, 0), "inbox": items}


@app.get("/", response_class=HTMLResponse)
def home():
    bots = ", ".join(sorted(runner.ADAPTERS)) or "none yet"
    return f"""<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{config.BOT_NAME}</title><style>body{{font-family:system-ui;max-width:640px;margin:40px auto;padding:0 16px;line-height:1.6}}
code{{background:#eee;padding:2px 5px;border-radius:4px}}</style></head><body>
<h1>⚔️ {config.BOT_NAME}</h1><p>The study squad bot that turns your group chat into a boss battle, and talks to your own Cubbie.</p>
<ol><li>Add the bot to your Discord channel or Telegram group.</li><li><code>/battle caches</code> to fight a topic boss together.</li>
<li><code>/link</code> to connect your Cubbie: it can send the squad challenges from your course material and text you your private recap.</li></ol>
<p>Bots online: {bots}</p></body></html>"""
