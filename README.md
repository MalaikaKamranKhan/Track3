<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/wordmark-badge.png">
  <img src="docs/img/wordmark-light.png" width="520" alt="Cramberry: the blue pixel berry next to the word Cramberry in pixel letters">
</picture>

### Your study squad's boss battle, right in Discord.

A pixel berry knight that turns a study group's Discord into a quiz game, and talks to each student's own Cubbie.

![Cubbie Hackathon](https://img.shields.io/badge/cubbie%20hackathon-track%203-1f6fe0?style=for-the-badge)
![Discord](https://img.shields.io/badge/lives%20in-discord-5865f2?style=for-the-badge)
![Cubbie](https://img.shields.io/badge/links%20to-your%20cubbie-3a8cef?style=for-the-badge)
![Python](https://img.shields.io/badge/python-3.10%2B-2b211b?style=for-the-badge)

<img src="docs/img/banner.png" width="860" alt="Cramberry, a blue pixel berry knight with a sword, facing a green lime topic boss">

<sub>Team wildberry · Cubbie Hackathon, Track 3 (Group Chat Assistant) · DevHacks Fall 2026</sub>

</div>

---

## Why it exists

Studying alone is boring, group study turns into chatting, and nobody knows what the group *actually* doesn't
understand.

Cramberry makes the group chat itself the study session. Someone says *"im so cooked on caches"*, and two minutes
later the whole squad is fighting the Caches Boss together. Every right answer drains its HP; every wrong one lets it
hit back. When the fight ends, the squad sees its weakest topic, and each student's **Cubbie** quietly texts them
what *they* missed.

---

## How Cubbie is in the loop

<div align="center"><img src="docs/img/flow.png" width="860" alt="How the squad is linked: each student's Cubbie reads their Canvas in private, sends a snapshot or a battle to the Cramberry server over the squad-link skill, Cramberry posts the game in the Discord group chat, the squad answers, and each private recap goes back only to that student's Cubbie"></div>

| | |
|---|---|
| **Cubbie reads Canvas** | Each student links their Cubbie with `/link`. On every check-in it shares a small course snapshot: course codes, this week's topics, due dates and what's submitted. Never grades or files. |
| **Cubbie builds battles** | *"Challenge my squad on caches"* → Cubbie writes questions from that student's own course material, **asks them first**, then Cramberry posts the battle. |
| **Cramberry spots the moment** | From everyone's snapshots it notices *"3 of you have the midterm Thursday"* or *"the squad keeps missing associativity"* and offers a battle. |
| **Recaps stay private** | The group sees questions, answers and scores. Your misses and @mentions go only to your own Cubbie, through your private key. |

Cubbie can't receive messages, so it always comes to Cramberry, like checking a mailbox. Cramberry keeps only the
last ~20 chat messages in memory (never stored), and `/quiet` turns chat reading off.

---

## The games

| Game | How it plays |
|---|---|
| **Boss Battle** `/battle <topic>` | Everyone answers A–D. Right answers damage the boss; wrong ones let it hit the squad back. 3 in a row is a ⚡ critical hit, there's one 🎲 50/50 per battle, and the final strike lets you 💰 wager half or all in. |
| **Two Truths & a Lie** `/lie <topic>` | Three statements, one is a plausible misconception. Find the lie before the dragonfruit liar wins. |
| **Explain It** `/explain <topic>` | Cramberry calls on someone to explain a concept in their own words. The AI grades it 0–10 and says what to add. Pass, and it's open floor for half XP. |
| **Daily Duel** `/daily` | One question a day to keep your streak and the squad streak alive. `/daily 8pm` schedules it, `/daily off` stops it. |

Every game gives XP. Levels run from **Freshman** to **Professor**, and badges like Boss Slayer, Perfect Round and
High Roller show on `/profile`.

---

## What the squad sees

Every battle posts a picture card after each question, drawn live by the bot. Each topic gets its own fruit boss,
and the same topic always gets the same one (caches is grape, recursion is lime, TCP is lemon).

| | |
|---|---|
| <img src="docs/img/card-battle.png" alt="Boss battle card: the lime Recursion Boss at full HP with a MISS stamp"> | <img src="docs/img/card-hurt.png" alt="Battle card: the lemon TCP boss at 30% HP, hurt, with a CRIT stamp"> |
| **The battle.** The boss and both HP bars. | **Crit!** Three right in a row. Below 40% the boss is hurt. |
| <img src="docs/img/card-liar.png" alt="Two Truths and a Lie card with the pink dragonfruit liar"> | <img src="docs/img/card-defeated.png" alt="Battle card: the kiwi Sorting Boss, grey and defeated"> |
| **Two Truths & a Lie.** The dragonfruit liar. | **Defeated.** The boss goes grey. |
| <img src="docs/img/card-victory.png" alt="Results card: VICTORY with a top-3 podium, Cramberry holding a sword and the beaten boss"> | <img src="docs/img/card-wiped.png" alt="Results card: SQUAD WIPED, the grape boss still angry"> |
| **Victory.** The podium and the squad's weak spot. | **Squad wiped.** Run it back. |

<div align="center">
<img src="docs/img/berry.png" width="49%" alt="The original blue berry, Cramberry holding a sword, and its purple evil twin">
<img src="docs/img/bosses.png" width="49%" alt="Fruit topic bosses: grape, lime, lemon, tangerine, kiwi, the dragonfruit liar, and a defeated boss">
</div>

<sub>Every character is one 24 × 24 pixel berry ([`squadbot/assets/mascot.svg`](squadbot/assets/mascot.svg)): give it a sword and it's Cramberry, recolour it with horns and fangs and it's a topic boss.</sub>

---

## "im cooked"

Say you're cooked in the group chat (*"im cooked"*, *"gonna fail"*, *"send help"*) and Cramberry rallies the whole
squad instead of letting you spiral:

> **Sunny is cooked. Squad, assemble!** Here's the game plan:
> `/battle` a 2-minute boss battle · `/explain` teach it back · `/plan` pick a study time · `/focus` group Pomodoro · `/radar` what's due

It never guesses your topic, stays quiet during games, answers at most once every 5 minutes, and *"we cooked that
exam"* doesn't count.

---

## Study tools

| Command | What it does |
|---|---|
| `/plan <topic>` | A poll for a study time. The starter locks it, everyone going gets pinged 30 min before, and linked Cubbies offer to add it to Google Calendar. |
| `/focus [minutes]` | Group Pomodoro. Join, focus, get pinged at the break. |
| `/radar` | Everything due in the next 7 days across the squad (from linked Cubbies). Also posts every morning at 9. |
| `/notes` | Upload slides or notes (PDF, txt, md), and battles on those topics use them. |
| `/insights` | What Cramberry knows: courses, this week's topics, deadlines, weak spots. |
| `/profile` · `/leaderboard` | Level, XP, badges, streaks, accuracy. |
| `/link` · `/ask_cubbie <topic>` | Connect your Cubbie, or ask every linked Cubbie to build a battle from Canvas. |
| `/quiet` · `/watch` | Stop or allow reading the chat. |

**Course-aware:** once a Cubbie has shared your courses, `/battle CSE230` means *your* CSE 230, not another
university's course with the same code.

---

## Run it

You need Python 3.10+, a Discord server you can add bots to, and optionally an AI key. With no key at all,
`LLM_PROVIDER=fake` runs on a built-in question bank.

**1. Install**

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env
```
<sub>macOS/Linux: `python3 -m venv .venv`, `.venv/bin/python -m pip install -r requirements.txt`, `cp .env.example .env`.</sub>

**2. Create the Discord bot**

1. [discord.com/developers/applications](https://discord.com/developers/applications) → **New Application** → "Cramberry". Upload [`docs/img/avatar.png`](docs/img/avatar.png) as the icon.
2. **Bot** tab → **Reset Token** → paste it into `DISCORD_TOKEN`. On the same page turn on **Message Content Intent**.
3. **OAuth2 → URL Generator** → scopes `bot` and `applications.commands`, permissions Send Messages, Read Message History, Embed Links, Attach Files. Open the link and add the bot to your server.
4. Right-click your server → **Copy Server ID** → `DISCORD_GUILD_ID`, so slash commands appear instantly.

**3. Pick an AI** (in `.env`)

| Provider | Setting |
|---|---|
| Gemini (free key from [AI Studio](https://aistudio.google.com/apikey)) | `LLM_PROVIDER=gemini`, `GEMINI_API_KEY=...` |
| Claude / OpenAI | `LLM_PROVIDER=anthropic` or `openai`, plus the matching key |
| No key | `LLM_PROVIDER=fake` |

**4. Start it**

```powershell
.venv\Scripts\python -m squadbot.main
```

One process runs the Discord bot, the scheduler and the API for Cubbie. Run **one copy per bot token**; two copies
answer everything twice.

**5. Give it an HTTPS address** (only needed for Cubbie)

```powershell
ngrok http --url=<your-free-static-domain> 8000        # or: cloudflared tunnel --url http://localhost:8000
```

Put that `https://` address in `PUBLIC_URL` in `.env` and in `SERVER` at the top of
[`cubbie-skill/squad-link/scripts/squad.py`](cubbie-skill/squad-link/scripts/squad.py), then restart the bot.

---

## Connect Cubbie

1. Push the repo with `SERVER` set, and text Cubbie the skill folder link (`…/tree/main/cubbie-skill/squad-link`). Reply yes to install.
2. In your Discord channel, type `/link`. Your key is shown only to you.
3. Text Cubbie *"link my study squad"* and paste the key on Cubbie's **secure page**, never in the chat.
4. Try *"challenge my squad on caches"* → say yes → the battle appears in Discord. Afterwards: *"how did the squad battle go?"*

---

## Demo in 3 minutes

1. Someone types *"midterm thursday, im so cooked on caches"* and Cramberry rallies the squad.
2. Malaika texts her **Cubbie** *"challenge my squad on caches from my CSE 230 notes"*, approves it, and *"📲 Malaika's Cubbie built this"* lands in Discord.
3. Judges press A–D on their own phones and watch the grape boss's HP drop and the podium form.
4. Malaika texts Cubbie *"how did we do?"* and gets a private recap with her missed question explained.
5. Show `/quiet` and the "asks before posting" step: privacy and consent built in.

---

## Under the hood

```text
squadbot/main.py                 one process: Discord bot + scheduler + FastAPI for Cubbie
squadbot/runner.py               every game and feature, buttons, commands, the scheduler
squadbot/engine.py               battle rules: damage, crits, 50/50, wagers, weak topics, "im cooked"
squadbot/cards.py · images.py    every message as an embed, plus the Pillow picture cards
squadbot/sprites.py              Cramberry and the fruit bosses, built from assets/mascot.svg
squadbot/llm.py                  questions, lies, grading (Gemini, Claude, OpenAI, Bedrock, offline)
squadbot/insights.py             Cubbie snapshots, right-moment suggestions, /radar
squadbot/api.py                  the HTTPS API the Cubbie skill calls
squadbot/adapters/discord_bot.py slash commands, buttons, embeds
cubbie-skill/squad-link/         the Cubbie Skill: SKILL.md + a standard-library script
```

```powershell
.venv\Scripts\python -m pip install pytest
.venv\Scripts\python -m pytest -q tests          # 27 tests, fully offline
```

The tests cover the battle rules, every game end to end with simulated button presses, the picture cards, and the
full Cubbie script → API → group battle → private recap loop over real HTTP.

<div align="center">

---

<img src="docs/img/wordmark-badge.png" width="240" alt="Cramberry">

*Nobody gets cooked alone.*

</div>
