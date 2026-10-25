<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/img/wordmark-badge.png">
  <img src="docs/img/wordmark-light.png" width="520" alt="Cramberry: the blue pixel berry next to the word Cramberry in pixel letters">
</picture>

### Turn your Discord study group chat into a cram battle.

**Cramberry** (cram + cranberry) is a Discord bot for study groups. When someone says "im cooked", it starts a
2-minute quiz the whole group plays together, and each person's Cubbie texts them what they got wrong.

![Cubbie Hackathon](https://img.shields.io/badge/cubbie%20hackathon-track%203-1f6fe0?style=for-the-badge)
![Discord](https://img.shields.io/badge/lives%20in-discord-5865f2?style=for-the-badge)
![Cubbie](https://img.shields.io/badge/links%20to-your%20cubbie-3a8cef?style=for-the-badge)
![License](https://img.shields.io/badge/license-MIT-2b211b?style=for-the-badge)

<img src="docs/img/banner.png" width="860" alt="Cramberry, a blue pixel berry knight with a sword, facing a green lime topic boss">

<sub>Team wildberry · Cubbie Hackathon, Track 3 (Group Chat Assistant) · DevHacks Fall 2026</sub>

**[How it works](#how-it-works)** · **[Cubbie](#cubbie-from-your-phone)** · **[Games](#the-games)** · **[Quick start](#quick-start)** · **[Setup guide](SETUP.md)**

</div>

---

## Why it exists

Studying alone is boring, group study turns into chatting, and nobody knows what the group doesn't understand.

Cramberry turns the group chat into the cram session. Someone says *"im so cooked on caches"*, and two minutes later
the whole group is fighting the Caches Boss: right answers drain its HP, wrong ones let it hit back. When the fight
ends, everyone sees the topic to review, and each person's **Cubbie** texts them what *they* missed.

---

## How it works

<div align="center"><img src="docs/img/flow.png" width="860" alt="How the squad is linked: each student's Cubbie reads their Canvas in private, sends a snapshot or a battle to the Cramberry server over the squad-link skill, Cramberry posts the game in the Discord group chat, the squad answers, and each private recap goes back only to that student's Cubbie"></div>

| | |
|---|---|
| **1. Your Cubbie checks Canvas** | Topics and due dates for your classes. Never grades or files. |
| **2. It writes a quiz from your notes** | And asks you before sending it to the group. |
| **3. Cramberry posts it in Discord** | Picture cards and A–D buttons in your group chat. |
| **4. Everyone answers** | Right answers hurt the boss; wrong ones hurt your team. |
| **5. Your results stay private** | Your rank and what you missed go only to your own Cubbie. |

Cramberry also spots the right moment from everyone's snapshots (*"3 of you have the midterm Thursday"*) and
offers a battle. It keeps only the last ~20 chat messages in memory, never stored, and `/quiet` turns chat reading
off. No Cubbie? Everything except the Cubbie features still works.

---

## Cubbie, from your phone

<div align="center"><img src="docs/img/cubbie-chat.png" width="860" alt="Two iMessage chats with Cubbie. Left: link my study squad, the private page for the key, linked to wildberry squad #general, then sharing a course snapshot. Right: challenge my squad on caches, Cubbie asks before posting, then a private recap"></div>

| Text Cubbie | What happens |
|---|---|
| *install https://github.com/MalaikaKamranKhan/Track3/blob/main/cubbie-skill/squad-link/SKILL.md* | Cubbie installs the squad-link skill |
| *link my study squad* | Cubbie sends a **private page**: paste the key from `/link` there, never in the chat. It confirms "Linked as … to wildberry squad's #general on Discord" and asks to share your course progress |
| *check my squad and share my course snapshot* | Your courses and deadlines reach Cramberry (`/radar`, `/insights`), and anything new from your group comes back |
| *challenge my squad on caches* | Cubbie writes the questions, asks *"Post this battle to your squad?"*, and posts only after you say yes |
| *how did the squad battle go?* | Your private recap: rank, what you missed and why |
| *update squad-link* | Re-installs the skill from GitHub, e.g. after the bot's server address changes |

Details in [SETUP.md → Connect Cubbie](SETUP.md#7-connect-cubbie).

---

## The games

| Game | How it plays |
|---|---|
| **Boss Battle** `/battle <topic>` | Everyone answers A–D. Right answers hurt the boss; wrong ones hurt your team. 3 in a row is a ⚡ critical hit, there's one 🎲 50/50 per battle, and on the last question you can 💰 wager half or all in. |
| **Two Truths & a Lie** `/lie <topic>` | Three statements, one false. Find the lie before the dragonfruit liar wins. |
| **Explain It** `/explain <topic>` | Cramberry picks someone to explain a concept in their own words. The AI scores it 0–10 and says what to add. Pass, and anyone can answer for half XP. |
| **Daily Duel** `/daily` | One question a day. Keep your streak and the group's streak alive. `/daily 8pm` schedules it, `/daily off` stops it. |

<div align="center"><img src="docs/img/bosses.png" width="860" alt="Fruit topic bosses: grape, lime, lemon, tangerine, kiwi, the dragonfruit liar, and a defeated boss"></div>

Each topic gets its own fruit boss, and the same topic always gets the same one: caches is grape, recursion is
lime, TCP is lemon. Below 40% HP a boss gets a bandage; at zero it turns grey.

---

## What your group sees

After every question, Cramberry posts a picture card, drawn live by the bot.

| | |
|---|---|
| <img src="docs/img/card-battle.png" alt="Boss battle card: the lime Recursion Boss at full HP with a MISS stamp"> | <img src="docs/img/card-hurt.png" alt="Battle card: the lemon TCP boss at 30% HP, hurt, with a CRIT stamp"> |
| **The battle.** The boss and both HP bars. | **Crit!** Three right in a row. The boss is hurt. |
| <img src="docs/img/card-liar.png" alt="Two Truths and a Lie card with the pink dragonfruit liar"> | <img src="docs/img/card-defeated.png" alt="Battle card: the kiwi Sorting Boss, grey and defeated"> |
| **Two Truths & a Lie.** The dragonfruit liar. | **Defeated.** The boss goes grey. |
| <img src="docs/img/card-victory.png" alt="Results card: VICTORY with a podium of Malaika, Sunny and Dhanush, Cramberry holding a sword and the beaten boss"> | <img src="docs/img/card-wiped.png" alt="Results card: SQUAD WIPED, the grape boss still angry"> |
| **Victory.** The podium and the topic to review. | **Lost.** It shows what to study next. |

---

## "im cooked"

Say you're cooked in the group chat (*"im cooked"*, *"gonna fail"*, *"send help"*) and Cramberry gets the whole
group studying with you.

<div align="center"><img src="docs/img/sos.png" width="860" alt="Discord: Sunny says they're cooked on caches, and Cramberry replies with a five-step game plan: battle, explain, plan, focus, radar"></div>

It never guesses your topic, stays quiet during games, answers at most once every 5 minutes, and *"we cooked that
exam"* doesn't count.

---

## Study tools

| Command | What it does |
|---|---|
| `/plan <topic>` | A poll for a study time. The starter locks it, everyone going gets pinged 30 min before, and linked Cubbies offer to add it to Google Calendar. |
| `/focus [minutes]` | Group Pomodoro. Join, focus, get pinged at the break. |
| `/radar` | Everything due in the next 7 days across the group (from linked Cubbies). Also posts every morning at 9. |
| `/notes` | Upload slides or notes (PDF, txt, md), and battles on those topics use them. |
| `/insights` | What Cramberry knows: courses, this week's topics, deadlines, weak spots. |
| `/profile` · `/leaderboard` | Level, XP, badges, streaks, accuracy. |
| `/link` · `/ask_cubbie <topic>` | Connect your Cubbie, or ask every linked Cubbie to build a battle from Canvas. |
| `/quiet` · `/watch` | Stop or allow reading the chat. |

<div align="center"><img src="docs/img/card-profile.png" width="860" alt="Profile card for Dhanush: level 3 Junior, an XP bar, and tiles for games, accuracy, streak, badges and total XP"></div>

Every game gives XP. Levels run from **Freshman** to **Professor**, and badges like Boss Slayer, Perfect Round and
High Roller show on `/profile`. Once a Cubbie has shared your courses, `/battle CSE230` means *your* CSE 230, not
another university's course with the same code.

---

## Quick start

Needs Python 3.10+ and a Discord bot token ([how to get one](SETUP.md#3-create-the-discord-bot)).

```powershell
git clone https://github.com/MalaikaKamranKhan/Track3.git
cd Track3
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
copy .env.example .env                     # add your DISCORD_TOKEN and DISCORD_GUILD_ID
.venv\Scripts\python -m cramberry.main
```

Then type `/battle caches` in your server. It runs without any AI key (`LLM_PROVIDER=fake` uses a built-in question
bank). Creating the Discord bot, AI keys, macOS/Linux commands, the HTTPS address for Cubbie, every setting and
troubleshooting are in the **[full setup guide](SETUP.md)**.

---

## Demo in 3 minutes

1. Sunny types *"midterm thursday, im so cooked on caches"* and Cramberry gets the group studying.
2. Malaika texts her **Cubbie** *"challenge my squad on caches from my CSE 230 notes"*, approves it, and *"📲 Malaika's Cubbie built this"* lands in Discord.
3. Judges press A–D on their own phones and watch the grape boss's HP drop and the podium form.
4. Malaika texts Cubbie *"how did the squad battle go?"* and gets a private recap with her missed question explained.
5. Show `/quiet` and the "asks before posting" step: privacy and consent built in.

---

## Under the hood

<div align="center"><img src="docs/img/berry.png" width="720" alt="The original blue berry, Cramberry holding a sword, and its purple evil twin"></div>

Every character is one 24 × 24 pixel berry ([`cramberry/assets/mascot.svg`](cramberry/assets/mascot.svg)): give it a
sword and it's Cramberry, recolour it with horns and fangs and it's a topic boss. All of it is drawn from data at
runtime, so the cards stay sharp at any size.

```text
cramberry/main.py                 one process: Discord bot + scheduler + FastAPI for Cubbie
cramberry/runner.py               every game and feature, buttons, commands, the scheduler
cramberry/engine.py               battle rules: damage, crits, 50/50, wagers, weak topics, "im cooked"
cramberry/cards.py · images.py    every message as an embed, plus the Pillow picture cards
cramberry/sprites.py              Cramberry and the fruit bosses, built from assets/mascot.svg
cramberry/llm.py                  questions, lies, grading (Gemini, Claude, OpenAI, Bedrock, offline)
cramberry/insights.py             Cubbie snapshots, right-moment suggestions, /radar
cramberry/api.py                  the HTTPS API the Cubbie skill calls
cramberry/adapters/discord_bot.py slash commands, buttons, embeds
cubbie-skill/squad-link/         the Cubbie Skill: SKILL.md + a standard-library script
tests/                           27 offline tests, from battle rules to the full Cubbie loop over HTTP
```

---

## Team

**Team wildberry**: **Malaika**, **Sunny** and **Dhanush**, three students who crammed Cramberry into one weekend.

## License and credits

Code: [MIT](LICENSE) © 2026 team wildberry. Use it, change it, share it; just keep our names on it.

- **Cubbie** and its mascot belong to [Cubbie](https://hackathon.cubbie.ai/); they appear here to show how the
  hackathon pieces connect.
- Fonts: [Outfit](cramberry/assets/fonts/Outfit-OFL.txt) and [Pixelify Sans](cramberry/assets/fonts/PixelifySans-OFL.txt),
  both under the SIL Open Font License.

<div align="center">

---

<img src="docs/img/wordmark-badge.png" width="240" alt="Cramberry">

*Nobody gets cooked alone.*

</div>
