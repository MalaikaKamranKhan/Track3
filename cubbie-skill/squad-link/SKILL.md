---
name: squad-link
description: Connects Cubbie to the student's Cramberry bot on Discord, to share course progress, answer the squad's battle requests and text them a private recap. Use when the student wants to link their study squad, check their squad, challenge or quiz their study group or group chat, or asks how a squad battle went or what they missed in the group.
---

# Squad Link

The Cramberry bot lives in a study group's Discord channel and runs "boss battle" quizzes there.
This Skill is the student's private side of it. Cubbie visits the Cramberry bot like a mailbox:

- Drop-off: a small course snapshot from Canvas (topics this week, what's due, what's submitted), so the bot can
  suggest a battle at the right moment, like when the whole squad has finished an assignment or has an exam soon.
- Pick-up: battle requests from the squad, the student's battle results, and messages where someone tagged them.

Cubbie never messages the group itself. Battles reach the group only through the Cramberry bot, and only after the
student says yes. The snapshot holds course codes, topic names, assignment titles, due dates and
submitted/not-submitted only: never grades, scores, files, feedback or messages.

## When to use

- "Link my study squad", "connect my Discord study group".
- "Check my squad", "anything from the squad?", "how did the squad battle go?", "what did I miss in the group?"
- "Challenge my squad on caches from my CSE 230 notes", "send my group a quiz on chapter 5".
- A scheduled Squad Link check-in runs.

Do not use it to quiz only the student here in the thread; Cubbie can do that on its own.

## Key

This Skill needs the student's personal squad key, saved in Cubbie as `SQUAD_API_KEY`. The student gets it by
typing `/link` in their group chat; the Cramberry bot shows the key only to them. If the key is not saved yet, tell
the student to do that, then send the secure page to save `SQUAD_API_KEY`. Never ask the student to paste the key
into the chat. Commands receive the key only when they name it, as in the commands below.

All commands run from this Skill's folder and use only Python's standard library.

## Steps: link the squad (first time)

1. Run `SQUAD_API_KEY="$SQUAD_API_KEY" python3 scripts/squad.py me` and tell the student which squad they joined.
2. Ask once: "Share your course progress with the squad? Only course codes, topic names, due dates and what
   you've submitted. No grades or files." Remember the answer. If they say no, skip the snapshot in every check-in.
3. Offer a check-in every 3 hours between 9 am and 10 pm (see Check-ins), then run a first check-in now.

## Steps: check in ("check my squad", or the scheduled check-in)

1. If the student agreed to share, build the snapshot from the student's Canvas: for each current course, the
   topics of this week's modules or announcements (short names, at most 5), assignments, quizzes and exams due in
   the next 14 days with their due dates, and assignments the student submitted in the last 7 days. If Canvas is
   not connected, skip the snapshot and tell the student once that connecting Canvas lets Cramberry help more.
   Save it as `snapshot.json` in exactly this shape (dates as YYYY-MM-DD):

   ```json
   {"courses": [{"code": "CSE 230", "name": "Computer Organization",
                 "topics": ["caches", "virtual memory"],
                 "upcoming": [{"title": "Midterm 2", "kind": "exam", "due": "2026-10-29", "topic": "caches"}],
                 "submitted": [{"title": "PSET 4", "topic": "caches"}]}]}
   ```

2. Run `SQUAD_API_KEY="$SQUAD_API_KEY" python3 scripts/squad.py checkin --snapshot-file snapshot.json`
   (without `--snapshot-file` when the student doesn't share).
3. Read the output lines and act on them:
   - REQUEST: someone in the squad asked for a battle. Text the student one line, for example:
     "Sashi asked the squad's Cubbies for a caches battle. Want me to make one from your CSE 230 notes and post it?"
     On yes, follow "Steps: post a battle" with that topic, course and the request id. On no, run
     `SQUAD_API_KEY="$SQUAD_API_KEY" python3 scripts/squad.py decline --request-id <id>`.
   - RESULT and MISSED: text whether the squad beat the boss and the student's points and rank in one line, then
     each missed question in one short line with the right answer and why. Offer a 3-question practice round here
     in the thread on those topics.
   - MENTION: text who tagged the student and what they said, and offer a short draft reply they can post.
   - SESSION: the squad locked a study session. Text one line with the time, topic and who's going, and offer to
     add it to the student's Google Calendar (60 minutes, titled "Study session: <topic>"). Add it only after
     they say yes. If Google isn't connected, offer a reminder 30 minutes before instead.
   - EXPLAIN: the student played Explain It. Text their score and the one thing to add next time, in one line.
   - NOTHING NEW (and no other lines): during a scheduled check-in, send nothing at all. When the student asked,
     say in one line that nothing is new.
   - SHARED and WEAK TOPICS: don't mention unless the student asks.

## Steps: post a battle

1. Find the topic and course from the request or from what the student said. If the course is missing, read the
   student's Canvas courses and upcoming exams for the next 14 days and suggest the soonest one.
2. Get material: anything the student sent in this conversation first, then the course materials in Canvas for
   that topic (search them and read the most relevant files or pages). If there is nothing to read, say the
   questions will be general, not from their course.
3. Write 5 multiple-choice questions from the material: 4 options each, exactly one right, a one-sentence
   explanation, and a 1 to 3 word sub-topic. Keep each question under 200 characters and each option under 80.
   Never copy questions from graded work. Save them as `questions.json`:

   ```json
   {"questions": [{"prompt": "...", "options": ["...", "...", "...", "..."], "answer": "B",
                   "explanation": "...", "topic": "..."}]}
   ```

4. Unless the student already said yes to this exact battle, show the topic, the number of questions and the
   first question, and ask: "Post this battle to your squad?" Do not post before the student says yes.
5. Run `SQUAD_API_KEY="$SQUAD_API_KEY" python3 scripts/squad.py challenge --topic "<topic>" --course "<course>" --questions-file questions.json`
   and add `--request-id <id>` when answering a REQUEST.
6. Tell the student in one line that the battle is live in their group, and remind them to play too.

## Check-ins

Offer one scheduled check-in every 3 hours from 9 am to 10 pm, and let the student change it. Create it only
after they say yes. Word it so it makes sense on its own later: "Squad Link check-in: if the student agreed to
share course progress, build snapshot.json from Canvas as the squad-link Skill describes; run the squad-link
checkin command; text the student only about REQUEST, RESULT, MENTION, SESSION or EXPLAIN lines."

## Replies

- Short, plain text, one idea per message. No headings, tables or bold markers.
- Lead with the outcome ("Squad beat the Cache Boss, you were #2 🥈"), then the details.
- Never show the squad key.

## When something fails

| Exit code | Meaning | What to do |
| --- | --- | --- |
| 2 | Bad snapshot, questions file or input | Fix the file to match the shape above and run again once |
| 3 | Key missing | Tell the student to type /link in their group chat, then send the secure page for `SQUAD_API_KEY` |
| 4 | Cramberry server unreachable | Say Cramberry can't be reached right now; during a scheduled check-in, stay quiet |
| 5 | Key rejected | Ask the student to type /link in the group again and save the new key on the secure page |
| 6 | A battle is already running, or Cramberry is offline | Pass on the message in one line and offer to try again later |
