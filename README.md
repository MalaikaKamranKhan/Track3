# ⚔️ Cramberry: your group chat's study boss battle, linked to your own Cubbie

**Cubbie Hackathon · Track 3 (Group Chat Assistant) · team wildberry · DevHacks Fall 2026**

Cramberry (cram + cranberry) is a pixel berry warrior that joins your study group on **Discord**. When the chat sounds like a midterm is coming
("im so cooked on caches"), it offers a quick **boss battle**: everyone answers multiple-choice questions with
buttons, every right answer knocks down the boss's HP, and the squad wins or loses together. Afterwards it posts a
leaderboard and the group's weakest topic.

The twist: each student can **link their own Cubbie** (the AI in their iMessage). Their Cubbie can build a battle
from *their* Canvas course material and post it to the group, and later texts them a **private recap**: their
rank, the questions they missed with explanations, and anyone who tagged them in the group.

**Why students need this:** studying alone is boring, group study turns into chatting, and nobody knows what the
group actually doesn't understand. Cramberry makes the group chat itself the study session, and Cubbie keeps the
personal follow-up private.

## How it fits together

```
 Your phone (private)                             Group chat (shared)
 ┌──────────────┐  squad-link Skill  ┌──────────────────┐   ┌──────────────┐
 │ Your Cubbie  │ ── HTTPS + key ──▶ │ Cramberry server │ ─▶│ Discord bot  │
 │ (iMessage)   │ ◀── your recap ─── │ games, AI        │   │ your server  │
 └──────────────┘                    └──────────────────┘   └──────────────┘
```

- **Cubbie → group:** "challenge my squad on caches" → Cubbie writes questions from Canvas → asks you → posts.
- **Cubbie check-ins (the mailbox):** every few hours, or when you text "check my squad", your Cubbie drops off a
  course snapshot from Canvas (topics, what's due, what you submitted) and picks up squad requests, your results
  and @mentions. Cubbie can't receive pushes, so it always comes to the bot.
- **Right-moment suggestions:** from everyone's snapshots the bot notices "all 4 of you submitted PSET 4",
  "3 of you have the midterm tomorrow" or "the squad keeps missing associativity" and offers a battle, with
  buttons to start one now or ask your Cubbies to build one from Canvas.
- **What's shared:** the group sees questions, answers and scores. Your misses and mentions go only to your own
  Cubbie, through your private key. The bot keeps the last ~20 chat messages in memory only (never stored) and
  `/quiet` turns chat reading off.
- **When it asks:** Cubbie asks before posting anything to the group; the bot asks the group before starting a battle.

## Games

| Game | How it plays |
| --- | --- |
| ⚔️ **Boss Battle** `/battle <topic>` | Everyone answers A-D. Right answers damage the boss, wrong ones let it hit the squad back. 3 in a row = ⚡ critical hit. One 🎲 50/50 per battle. 💰 Final strike: wager half or ALL IN. |
| 🕵️ **Two Truths & a Lie** `/lie <topic>` | Three statements, one is a plausible misconception. Find the lie. |
| 🎤 **Explain It** `/explain <topic>` | The bot calls on someone to explain a concept in their own words; the AI grades it 0-10 with what they covered and what to add. Pass and it's open floor for half XP. |
| 📅 **Daily Duel** `/daily` | One question a day. Keep your 🔥 streak and the squad streak alive. `/daily 8pm` schedules it, `/daily off` stops it. |

Every game gives XP: levels go 🐣 Freshman → 👑 Professor, and badges (🗡️ Boss Slayer, 🎯 Perfect Round, 🔥 On Fire,
🕵️ Lie Detector, 🧠 Big Brain, 💰 High Roller, 📅 Habit Builder, 🍅 Deep Work) show on `/profile`.

## Study tools

| Command | What it does |
| --- | --- |
| `/plan <topic>` | Poll for a study session time (next 3 evenings, or `times: tue 7pm, wed 6pm`). Tap times, the starter locks it, everyone going gets pinged 30 min before and at the start, and linked Cubbies offer to add it to Google Calendar. |
| `/focus [minutes]` | Group Pomodoro. Join, focus, get pinged at the break, +20 XP. |
| `/radar` | What's due in the next 7 days across the squad (from linked Cubbies). Also posts every morning at 9. |
| `/notes` | Upload slides or notes (PDF, txt, md); battles on those topics use them. |
| `/insights` | What the bot knows: courses, this week's topics, deadlines, weak spots. |
| `/profile`, `/leaderboard` | Levels, XP, badges, streaks, accuracy. |
| `/link`, `/ask_cubbie <topic>` | Connect your Cubbie; ask every linked Cubbie to build a battle from Canvas. |
| `/quiet`, `/watch` | Stop or allow reading the chat for study moments. |

**Course-aware:** when a linked Cubbie has shared your courses, `/battle CSE230` becomes your CSE 230 (course name and
this week's topics go to the AI), not another university's course with the same code.

## Run it (15 minutes)

```bash
python3 -m venv .venv && source .venv/bin/activate      # Python 3.10+
pip install -r requirements.txt
cp .env.example .env                                      # then fill it in (below)
python -m squadbot.main
```

It works with no keys at all: `LLM_PROVIDER=fake` uses a built-in caches question bank, perfect for a demo.

### Discord bot token
1. https://discord.com/developers/applications → **New Application** → name it "Cramberry".
2. **Bot** tab → **Reset Token** → copy into `DISCORD_TOKEN`. On the same page turn on **Message Content Intent**.
3. **OAuth2 → URL Generator**: scopes `bot` and `applications.commands`; permissions Send Messages,
   Read Message History, Embed Links. Open the URL and add the bot to your server.
4. Right-click your server → Copy Server ID (turn on Developer Mode in Discord settings if missing) →
   `DISCORD_GUILD_ID`, so slash commands appear instantly.

### AI key (pick one)
- **Gemini** (free, 2 min): https://aistudio.google.com/apikey → `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=...`
- **AWS Bedrock** (sponsor credits): `pip install boto3`, enable model access in the Bedrock console,
  set `LLM_PROVIDER=bedrock` plus AWS credentials; default model is Amazon Nova Lite.
- **Claude** or **OpenAI**: `LLM_PROVIDER=anthropic` / `openai` with the matching key.
- `LLM_MODEL` overrides the default model name if a provider rejects it.

### Make it reachable over HTTPS (needed for Cubbie)
Fastest for tonight, from the laptop running the bot:
```bash
cloudflared tunnel --url http://localhost:8000     # prints https://<random>.trycloudflare.com
```
Put that URL in `PUBLIC_URL` (restart the bot) and in `SERVER` at the top of `cubbie-skill/squad-link/scripts/squad.py`.
For something that stays up without your laptop, deploy to Railway or Render as a web service with start command
`python -m squadbot.main` and the same environment variables (free tiers may sleep when idle).

## Connect Cubbie

1. Push `cubbie-skill/squad-link/` to a **public** GitHub repo (with `SERVER` set to your https URL).
2. Text Cubbie the folder link, e.g. `https://github.com/<you>/<repo>/tree/main/cubbie-skill/squad-link`, reply yes.
3. In the group chat type `/link`, copy your key.
4. Text Cubbie "link my study squad". Paste the key on Cubbie's **secure page** (never in the chat).
5. Try: "challenge my squad on caches" → say yes → the battle appears in the group. Play it, then text Cubbie
   "how did the squad battle go?".

## Demo script for judges (3 minutes)
1. Group chat: someone types "midterm thursday, im so cooked on caches" → Cramberry offers a battle.
2. Instead, Malaika texts her **Cubbie** "challenge my squad on caches from my CSE 230 notes" → approves →
   "📲 Malaika's Cubbie sent a challenge" lands in Discord.
3. Hand judges the Discord link: they press A–D buttons and watch the HP bar drop and the leaderboard form.
4. Malaika texts Cubbie "how did we do?" → private recap with her missed question explained.
5. Show `/quiet` and the "asks before posting" step: privacy and consent built in.

## Tests
```bash
pip install pytest && python -m pytest -q tests
```
Covers the rules (crits, the boss hitting back, 50/50, wagers, levels, streaks, time parsing, card text), every
game end to end with simulated button presses (boss battle, Two Truths, Explain It, Daily Duel, focus, plan,
radar, reminders), and the full Cubbie script → API → group battle → private recap loop over real HTTP.

## Code map
- `squadbot/engine.py` · rules: scoring, boss and squad HP, crits, 50/50, wagers, weak topics
- `squadbot/runner.py` · every game and feature, buttons, commands, the scheduler (adapter interface)
- `squadbot/cards.py` · every message as a Card (Discord embed)
- `squadbot/progress.py` · XP, levels, badges, Daily Duel streaks
- `squadbot/planner.py` · study session polls, time parsing, reminders
- `squadbot/adapters/` · the Discord bot
- `squadbot/llm.py` · question generation and study-moment detection (Gemini, Bedrock, Claude, OpenAI, offline)
- `squadbot/api.py` · HTTPS API the Cubbie Skill calls
- `cubbie-skill/squad-link/` · the Cubbie Skill (SKILL.md + standard-library script)
