#!/usr/bin/env python3
"""Talks to the Squad bot server for the squad-link Cubbie Skill. Standard library only.

  SQUAD_API_KEY="$SQUAD_API_KEY" python3 scripts/squad.py me
  SQUAD_API_KEY="$SQUAD_API_KEY" python3 scripts/squad.py checkin --snapshot-file snapshot.json
  SQUAD_API_KEY="$SQUAD_API_KEY" python3 scripts/squad.py checkin            (pick-up only)
  SQUAD_API_KEY="$SQUAD_API_KEY" python3 scripts/squad.py challenge --topic "caches" --questions-file questions.json [--course "CSE 230"] [--request-id ID]
  SQUAD_API_KEY="$SQUAD_API_KEY" python3 scripts/squad.py decline --request-id ID

Exit codes: 0 ok, 2 bad input, 3 key missing, 4 server unreachable, 5 key rejected, 6 squad busy or bot offline.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# Set this to your deployed server after you deploy it (must be https).
SERVER = "https://numeral-caboose-operation.ngrok-free.dev"


def call(server, key, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(server.rstrip("/") + path, data=data, method=method,
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "User-Agent": "squad-link-skill/1.2"})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        try:
            detail = json.loads(exc.read().decode()).get("detail", "")
        except ValueError:
            detail = ""
        if exc.code == 401:
            fail(5, "Squad key rejected. Run /link in the group chat and save the new key as SQUAD_API_KEY.")
        if exc.code in (409, 503):
            fail(6, detail or "The squad is busy or the bot is offline.")
        fail(2, f"Server said: {detail or exc.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        fail(4, f"Squad server unreachable ({exc}).")


def fail(code, message):
    print(message)
    sys.exit(code)


def ago(ts):
    """Relative time, so the sandbox's time zone doesn't matter."""
    if not ts:
        return ""
    mins = max(0, int((time.time() - ts) // 60))
    if mins < 60:
        return f"({mins} min ago)"
    if mins < 48 * 60:
        return f"({mins // 60} h ago)"
    return f"({mins // 1440} days ago)"


def read_json(path, what):
    try:
        with open(path) as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        fail(2, f"Can't read {what} file {path}: {exc}")


def cmd_me(args, key):
    me = call(args.server, key, "GET", "/api/me")
    running = " A battle is running right now." if me["battle_running"] else ""
    print(f"Linked as {me['player']} to {me['squad']} on {me['platform']} ({me['members']} members).{running}")


def cmd_checkin(args, key):
    body = {"keep": args.keep}
    if args.snapshot_file:
        body["snapshot"] = read_json(args.snapshot_file, "snapshot")
    res = call(args.server, key, "POST", "/api/checkin", body)
    lines = []
    if res["snapshot_shared"]:
        lines.append(f"SHARED course snapshot with {res['squad']}.")
    for r in res["requests"]:
        course = f" course={r['course']}" if r["course"] else ""
        lines.append(f"REQUEST id={r['id']} topic=\"{r['topic']}\"{course} from={r['by']} {ago(r['at'])}: "
                     f"{r['by']} asked the squad's Cubbies for a battle on {r['topic']}.")
    for item in res["inbox"]:
        if item["type"] == "result":
            outcome = "beat" if item["boss_defeated"] else "lost to"
            lines.append(f"RESULT {ago(item['at'])}: squad {outcome} the {item['topic']} boss. "
                         f"You: {item['points']} pts, #{item['rank']} of {item['players']}.")
            for m in item["missed"][:5]:
                why = f" Why: {m['explanation']}" if m["explanation"] else ""
                lines.append(f"  MISSED [{m['topic']}]: {m['prompt']} Right answer: {m['right']}.{why}")
        elif item["type"] == "mention":
            lines.append(f"MENTION {ago(item['at'])} from {item['from']} in {item['squad']}: {item['text']}")
        elif item["type"] == "session":
            others = ", ".join(item.get("with") or []) or "the squad"
            lines.append(f"SESSION start={item['start']} label=\"{item['label']}\" topic=\"{item['topic']}\" "
                         f"with={others}: the squad locked a study session in {item['squad']}.")
        elif item["type"] == "explain":
            missed = "; ".join(item.get("missed") or []) or "nothing"
            lines.append(f"EXPLAIN {ago(item['at'])}: you explained {item['concept']} and scored {item['score']}/10. "
                         f"Feedback: {item['feedback']} Missed: {missed}.")
    if not res["requests"] and not res["inbox"]:
        lines.append("NOTHING NEW for the student.")
    weak = ", ".join(res["weak_topics"]) or "none yet"
    lines.append(f"WEAK TOPICS so far: {weak}. Total squad points: {res['total_points']}.")
    print("\n".join(lines)[:7500])


def cmd_challenge(args, key):
    body = {"topic": args.topic, "course": args.course or "", "request_id": args.request_id or ""}
    if args.questions_file:
        data = read_json(args.questions_file, "questions")
        body["questions"] = data["questions"] if isinstance(data, dict) else data
    elif args.material_file:
        try:
            with open(args.material_file) as fh:
                body["material"] = fh.read()[:20000]
        except OSError as exc:
            fail(2, f"Can't read {args.material_file}: {exc}")
    res = call(args.server, key, "POST", "/api/challenge", body)
    print(f"Posted a {res['questions']}-question {args.topic} boss battle to {res['squad']} on {res['platform']}.")


def cmd_decline(args, key):
    call(args.server, key, "POST", f"/api/requests/{args.request_id}/decline", {})
    print("Declined. The squad's other Cubbies can still answer it.")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--server", default=SERVER)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("me")
    for name in ("checkin", "results"):
        c = sub.add_parser(name)
        c.add_argument("--snapshot-file")
        c.add_argument("--keep", action="store_true", help="don't mark results as read")
    ch = sub.add_parser("challenge")
    ch.add_argument("--topic", required=True)
    ch.add_argument("--course")
    ch.add_argument("--request-id")
    src = ch.add_mutually_exclusive_group()
    src.add_argument("--questions-file")
    src.add_argument("--material-file")
    d = sub.add_parser("decline")
    d.add_argument("--request-id", required=True)
    args = p.parse_args()

    key = os.environ.get("SQUAD_API_KEY", "").strip()
    if not key:
        fail(3, "SQUAD_API_KEY is not saved.")
    local = args.server.startswith(("http://localhost", "http://127.0.0.1"))
    if not args.server.startswith("https://") and not local:
        fail(2, "The server address must start with https://")
    if "YOUR-SQUAD-SERVER" in args.server:
        fail(4, "This Skill's server address hasn't been set yet (SERVER in scripts/squad.py).")
    handlers = {"me": cmd_me, "checkin": cmd_checkin, "results": cmd_checkin,
                "challenge": cmd_challenge, "decline": cmd_decline}
    handlers[args.cmd](args, key)


if __name__ == "__main__":
    main()
