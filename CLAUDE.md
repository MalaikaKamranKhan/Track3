# Cramberry: context for Claude

Read this first. It's the handoff for anyone (human or Claude) picking up the code. Paths are relative to the repo
root (the folder with `README.md`; on Malaika's laptop it may be named `squadbot` or `cramberry`).

## What this is

**Cramberry** is a Discord study bot for the Cubbie Hackathon (Track 3, Group Chat Assistant), team wildberry,
DevHacks Fall 2026. It turns a study group's Discord channel into multiplayer quiz games (boss battles, Two Truths &
a Lie, Explain It, Daily Duel) plus study tools (session polls, group Pomodoro, deadline radar, notes). Each student
can link their own **Cubbie** (a personal AI in iMessage) through the `squad-link` Cubbie Skill: Cubbie shares a
Canvas course snapshot, can post battles built from the student's course material, and texts them a private recap.

## The naming rule (don't break this)

- **"Cramberry" is the bot.** Anything where the bot names or describes itself says Cramberry, ideally via
  `config.BOT_NAME` (default `"Cramberry"`).
- **"Squad" / "the squad" is the study group.** "Squad HP", "Squad leaderboard", "Squad weak spot", "squad streak",
  "your study squad" all stay.
- **Code identifiers keep "squad"**: the `squadbot` package, the `Squad` class, `squad.py`, the `squad-link` skill
  folder and "Squad Link" skill name, API routes, env vars like `SQUAD_API_KEY`. Renaming them breaks the installed
  Cubbie Skill and `python -m squadbot.main`.
- Telegram support was removed on purpose. Discord is the only chat app. Don't add it back.

## Run and test

```bash
# Windows (how the team runs it)
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt pytest
copy .env.example .env                     # fill in DISCORD_TOKEN etc. Never commit .env
.venv\Scripts\python -m squadbot.main      # API on :8000 + Discord bot + scheduler, one process
.venv\Scripts\python -m pytest -q tests    # 27 tests, ~45 s, fully offline
```
macOS/Linux: same with `.venv/bin/python`. Python 3.10+ (the team uses 3.14).

- The bot loads code at startup. **After any change: Ctrl+C and start it again.** Committing alone changes nothing.
- **Only one copy of the bot per Discord token.** Two teammates running the same token = every reply twice.
  For your own testing, make your own Discord app + test server and use your own token.
- `LLM_PROVIDER=fake` works with no keys (built-in caches questions). The team uses `gemini`.
- State lives in `data/state.json` (gitignored), so each machine starts with empty squads, XP and links.
- Tests set their own env in `tests/conftest.py` (fake LLM, temp data dir, tiny timers). They never touch `data/`.

## Layout

```
squadbot/                 the Python package (keep the name)
  main.py                 entry point: uvicorn API + Discord adapter + runner.scheduler(), one asyncio process
  config.py               every setting, from env vars / .env (see .env.example)
  runner.py               all games and features, chat-app agnostic: commands, buttons, chat watching, scheduler
  engine.py               pure battle rules: scoring, boss + squad HP, crits, 50/50, wagers, weak topics,
                          study-moment words, "im cooked" PANIC regex
  cards.py                every message as a Card(title, body, color, fields, footer, image) + esc()/plain()
  images.py               Pillow picture cards: battle(), results() podium, profile(). Wrapped in @safe:
                          a drawing error returns None and the card is sent without a picture
  sprites.py              pixel characters from assets/mascot.svg: hero() (berry + sword), evil() fruit bosses,
                          PALETTES, FRUITS, fruit_for(topic), boss_image()
  progress.py             XP, 8 levels (Freshman 0 → Professor 3000), 8 badges, Daily Duel streaks
  planner.py              /plan polls: time parsing, votes, locking, reminders
  insights.py             Cubbie course snapshots, right-moment suggestions, battle requests, notes, /radar data
  notes.py                uploaded .pdf/.txt/.md/.csv → text for question generation
  llm.py                  prompts + providers (gemini, anthropic, openai, bedrock, fake): questions, lies,
                          explain items, grading, detect_moment()
  store.py                dataclasses Question, Game, Squad, Link + Store (one JSON file, a lock, save())
  api.py                  FastAPI for the Cubbie Skill (Bearer = the student's squad key)
  adapters/discord_bot.py Discord: Cards → embeds (+ PNG attachment), Buttons → components, slash commands
  assets/mascot.svg       the 24×24 blue berry everything is built from
  assets/kit/             mascot kit sprites (32×32): poses/cramberry-{idle,wave,victory,hit,thinking,sleep}.svg,
                          boss/topic-boss.svg, emoji/{sword,hp-heart}.svg, favicon/favicon.svg
  assets/fonts/           Outfit (text) + Pixelify Sans (labels), OFL
cubbie-skill/squad-link/  the Cubbie Skill: SKILL.md (instructions Cubbie follows) + scripts/squad.py (stdlib client)
docs/make_images.py       renders every README picture into docs/img/ from the real code
tests/                    conftest.py (FakeAdapter), test_rules, test_games, test_images, test_insights, test_bridge
```

## How the pieces talk

- **Runner ↔ chat app:** `runner.Adapter` is a 2-method protocol (`send(chat_id, card, buttons, mentions,
  reply_to)` → handle, `edit(chat_id, handle, card, buttons)`). `runner.register(adapter)` keys it by `platform`.
  The Discord adapter forwards slash commands to `runner.command(squad, name, uid, uname, args)` → `Reply`, button
  presses to `runner.press(token, uid, name, handle)`, and every message to `runner.on_chat_message(...)`.
- **Buttons:** `runner.token(kind, *data)` stores an action and returns a short id; `press()` switches on `kind`
  (`ans`, `fifty`, `wager`, `start`, `explain`, `ask`, `dismiss`, `plan_*`, `focus_*`).
- **Chat watching**, in order (`runner.on_chat_message`): Explain It answers → `/quiet` stops everything → keep
  the last 20 messages in memory → **`engine.is_panic`** ("im cooked", "gonna fail", "send help"…) posts
  `cards.sos(name)` to the whole channel. It never guesses a topic: it lists `/battle`, `/explain`, `/plan`,
  `/focus`, `/radar`, and Discord's own option box asks for the topic. Limit: one per `PANIC_COOLDOWN_MINUTES`
  (5) per chat, silent during games. Otherwise the older study-moment path: 30-min nudge cooldown → study words →
  at most one LLM call a minute → Cubbie-snapshot suggestion or `llm.detect_moment` → "👀 Study moment spotted"
  offer with battle buttons.
- **A battle:** `start_game` (LLM questions, course-aware via `insights.resolve`) → `_run` posts each question with
  A-D buttons for `QUESTION_SECONDS` → `engine.close_question` (damage, crits on a 3-streak +50, boss hits back) →
  reveal card with `images.battle()` → final-strike wager → `_finish`: results card with `images.results()` podium,
  XP/badges, and a `result` + `missed` item in each linked student's Cubbie inbox.
- **Picture cards:** the boss colour comes from `sprites.fruit_for(game.topic)` (grape, lime, lemon, tangerine,
  kiwi; same topic = same fruit); Two Truths uses the pink `"lie"` palette; mood is angry / hurt (<40% HP) / dead.
  `assets/boss.png` or `assets/boss.svg`, if present, replaces the generated boss.
- **Cubbie bridge (`api.py`):** `GET /health`, `GET /api/me`, `POST /api/challenge` (post a battle from Cubbie's
  questions), `POST /api/checkin` (drop a course snapshot, pick up inbox items: REQUEST, RESULT, MISSED, MENTION,
  SESSION, EXPLAIN), `POST /api/requests/{id}/decline`, `GET /api/results`, `GET /` (a small home page).
  `scripts/squad.py` has subcommands `me`, `checkin`, `results`, `challenge`, `decline`, and exit codes
  2 bad input, 3 key missing, 4 server unreachable, 5 key rejected, 6 busy/offline (SKILL.md maps each to a reply).

## Config (env vars, see `.env.example`)

`BOT_NAME` (Cramberry) · `DISCORD_TOKEN` · `DISCORD_GUILD_ID` (instant slash-command sync for one server) ·
`PUBLIC_URL` · `PORT` (8000) · `DATA_DIR` · `IMAGES` (on/off) · `LLM_PROVIDER` · `LLM_MODEL` · `GEMINI_API_KEY` /
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `AWS_REGION` · game tuning: `QUESTIONS_PER_BATTLE` (5),
`QUESTION_SECONDS` (25), `LIE_SECONDS`, `WAGER_SECONDS`, `EXPLAIN_ROUNDS`, `EXPLAIN_SECONDS`,
`OPEN_FLOOR_SECONDS`, `DAILY_SECONDS`, `DAILY_NOW_SECONDS`, `NUDGE_COOLDOWN_MINUTES` (30),
`PANIC_COOLDOWN_MINUTES` (5), `SCHEDULER_SECONDS`, `INTRO_PAUSE`, `REVEAL_PAUSE`.

## Conventions

- Match the surrounding code: short docstrings on public functions, few comments, type hints, lines ≤ ~120,
  `from __future__ import annotations`, LF line endings.
- Anything from a user or the AI goes through `cards.esc()` before it lands in card text.
- New features get a test, using `FakeAdapter` and `runner.press(...)` like `tests/test_games.py`. Tests must stay
  offline. Run the whole suite before committing.
- Picture-card or sprite changes: also run `python docs/make_images.py` and check `docs/img/` so the README matches.
- Brand: ink `#2b211b`, blue deep `#1b4fa8`, blue `#1f6fe0`, blue mid `#3a8cef`, blush `#f3a6b8`, white, gold
  `#fde39a`, wildberry `#b8326e`; cream `#f6f0e4` and ink black `#0f1015` backgrounds. Pixel sprites only at
  whole-number scales with NEAREST resampling.
- Commit messages: short and imperative ("Reply to 'im cooked' with the squad's next steps").

## Gotchas

- **Message Content Intent** must be on (Developer Portal → Bot), or the bot never sees normal messages and
  "im cooked" / study moments never fire.
- **The tunnel URL changes** every time `cloudflared tunnel --url http://localhost:8000` restarts. Then update
  `PUBLIC_URL` in `.env` *and* `SERVER` at the top of `cubbie-skill/squad-link/scripts/squad.py`, commit, push, and
  the Cubbie Skill picks it up from GitHub.
- The Discord display name and avatar come from the Developer Portal, not the code. The icon is `docs/img/avatar.png`.
- On Windows, start everything with `.venv\Scripts\python` (pip via `-m pip`). Renaming the project folder only works
  with VS Code, terminals and the bot all closed.
- `.env` and `data/` are gitignored. Never print or commit tokens or keys, and never paste them in chat.

## History (newest first)

- Fruit bosses (grape, lime, lemon, tangerine, kiwi, dragonfruit liar), mascot kit assets in `assets/kit/`, README
  rebuilt around generated images (`docs/make_images.py`).
- "im cooked" → the 🆘 squad rally card (`engine.PANIC`, `runner._answer_panic`, `cards.sos`).
- Renamed the bot Squad → Cramberry (names only, identifiers kept) and removed Telegram.
- Berry sprites: the cartoon boss became a pixel evil twin of the mascot; the hero berry holds a sword on the podium.
- Picture cards (Pillow) for battles, results and profiles.

## Ideas on deck

- More README art from Claude Design (prompt: `cramberry-claude-design-prompt.md`, one folder above the repo on
  Malaika's laptop): social preview, privacy diagram, battle loop, games grid, XP ladder, "im cooked" chat mock, setup.
- Use the kit poses on cards (e.g. `cramberry-victory` on a win, `cramberry-hit` on a wipe, `cramberry-sleep` for /quiet).
- Rename the GitHub repo (Track3 → cramberry) and re-share the skill link with Cubbie.
- Deploy somewhere always-on (Railway/Render) so the tunnel URL stops changing.
