"""Telegram adapter: renders Cards as HTML messages, Buttons as inline keyboards, and forwards commands, presses
and messages to the runner.

Bot setup (@BotFather): /newbot -> copy the token. To let the bot see normal group messages (study-moment
detection, Explain It answers, mentions), send /setprivacy to BotFather and choose Disable. Commands, buttons and
replies to the bot's own messages work either way.
"""
from __future__ import annotations

import html
import logging

from telegram import BotCommand, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatAction, ChatMemberStatus, ChatType, ParseMode
from telegram.error import BadRequest, Forbidden, TelegramError
from telegram.ext import (Application, CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler,
                          filters)

from .. import cards, engine, runner
from ..cards import Card, to_telegram_html
from ..store import store

log = logging.getLogger("squad.telegram")

COMMANDS = [("battle", "Boss battle on a topic"), ("lie", "Two Truths & a Lie"),
            ("explain", "Explain It, AI-graded"), ("daily", "Daily Duel (or /daily 8pm to schedule)"),
            ("plan", "Pick a study session time"), ("focus", "Group Pomodoro"), ("radar", "What's due this week"),
            ("profile", "Your level, XP and badges"), ("leaderboard", "Squad XP ranking"),
            ("insights", "What I know about your courses"), ("ask_cubbie", "Ask linked Cubbies for a battle"),
            ("link", "Connect your Cubbie"), ("notes", "How to upload notes"), ("quiet", "Stop reading the chat"),
            ("watch", "Suggest battles at study moments"), ("help", "Everything I can do")]


def _name(user) -> str:
    return user.first_name or user.username or str(user.id)


def _squad(chat):
    return store.squad("telegram", chat.id, chat.title or "study squad")


def keyboard(buttons) -> InlineKeyboardMarkup | None:
    if not buttons:
        return None
    rows: dict[int, list] = {}
    for b in buttons:
        rows.setdefault(b.row, []).append(InlineKeyboardButton(b.label[:60], callback_data=f"a:{b.token}"))
    return InlineKeyboardMarkup([rows[r] for r in sorted(rows)])


class TelegramAdapter:
    platform = "telegram"

    def __init__(self, token: str):
        self.app = Application.builder().token(token).build()
        self.usernames: dict[str, int] = {}         # lowercase @username -> user id
        a = self.app
        a.add_handler(CommandHandler("start", self.cmd_start))
        a.add_handler(CommandHandler("link", self.cmd_link))
        a.add_handler(CommandHandler("notes", self.cmd_notes_help))
        for name, _ in COMMANDS:
            if name not in ("link", "notes"):
                a.add_handler(CommandHandler(name, self.cmd_generic))
        a.add_handler(CallbackQueryHandler(self.on_press, pattern=r"^a:"))
        a.add_handler(MessageHandler(filters.Document.ALL & filters.ChatType.GROUPS, self.on_document))
        a.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS, self.on_message))

    # Adapter interface ------------------------------------------------------
    async def send(self, chat_id: str, card: Card, buttons=None, mentions=None, reply_to=None):
        text = to_telegram_html(card)
        if mentions:
            tags = " ".join(f'<a href="tg://user?id={uid}">{html.escape(name)}</a>' for uid, name in mentions)
            text = f"{tags}\n{text}"
        return await self.app.bot.send_message(
            int(chat_id), text, parse_mode=ParseMode.HTML, reply_markup=keyboard(buttons),
            reply_to_message_id=getattr(reply_to, "message_id", None), disable_web_page_preview=True)

    async def edit(self, chat_id: str, handle, card=None, buttons=None) -> None:
        try:
            if card is not None:
                await self.app.bot.edit_message_text(
                    to_telegram_html(card), chat_id=int(chat_id), message_id=handle.message_id,
                    parse_mode=ParseMode.HTML, reply_markup=keyboard(buttons) if buttons is not None else None,
                    disable_web_page_preview=True)
            elif buttons is not None:
                await self.app.bot.edit_message_reply_markup(int(chat_id), handle.message_id,
                                                             reply_markup=keyboard(buttons))
        except BadRequest as exc:
            if "not modified" not in str(exc).lower():
                raise

    async def _reply(self, update: Update, reply: runner.Reply):
        if reply.card is None:
            return
        if reply.private and update.effective_chat.type != ChatType.PRIVATE:
            try:
                await self.send(str(update.effective_user.id), reply.card, reply.buttons)
                await update.effective_message.reply_text("📬 Sent you a DM.")
                return
            except Forbidden:
                pass  # can't DM someone who never started the bot; answer in the group instead
        await self.send(str(update.effective_chat.id), reply.card, reply.buttons,
                        reply_to=update.effective_message)

    # commands -----------------------------------------------------------------
    async def cmd_generic(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        msg, chat, user = update.effective_message, update.effective_chat, update.effective_user
        name = msg.text.split()[0][1:].split("@")[0].lower()
        if chat.type == ChatType.PRIVATE and name not in ("help", "profile", "leaderboard"):
            await msg.reply_text("I live in group chats. Add me to your study group, then use /" + name + " there!")
            return
        words = list(ctx.args or [])
        args: dict = {}
        if name in ("battle", "lie", "explain", "ask_cubbie"):
            args["topic"] = " ".join(words)
        elif name == "daily":
            first = words[0].lower() if words else ""
            if first and (first in ("off", "stop") or runner._parse_clock(first)):
                args["at"] = first
            else:
                args["topic"] = " ".join(words)
        elif name == "plan":
            topic, _, times = " ".join(words).partition("|")
            args.update(topic=topic.strip(), times=times.strip())
        elif name == "focus":
            if words and words[0].replace(".", "", 1).isdigit():
                args["minutes"] = words.pop(0)
            args["topic"] = " ".join(words)
        elif name == "profile" and msg.reply_to_message and msg.reply_to_message.from_user:
            target = msg.reply_to_message.from_user
            args.update(target_id=target.id, target_name=_name(target))
        if name in ("battle", "lie", "explain", "daily"):
            try:
                await ctx.bot.send_chat_action(chat.id, ChatAction.TYPING)
            except TelegramError:
                pass
        squad = _squad(chat)
        try:
            reply = await runner.command(squad, name, user.id, _name(user), args)
        except Exception:  # noqa: BLE001
            log.exception("/%s failed", name)
            await msg.reply_text("Something went wrong 😵 Try again in a moment.")
            return
        await self._reply(update, reply)

    async def cmd_start(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        msg, user = update.effective_message, update.effective_user
        payload = ctx.args[0] if ctx.args else ""
        if update.effective_chat.type == ChatType.PRIVATE and payload.startswith("link_"):
            chat_id = payload[5:]
            squad = store.squads.get(f"telegram:{chat_id}")
            try:
                member = await ctx.bot.get_chat_member(int(chat_id), user.id)
                in_group = member.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
            except (TelegramError, ValueError):
                in_group = False
            if not squad or not in_group:
                await msg.reply_text("I couldn't find you in that group. Use /link inside the group chat.")
                return
            store.add_member(squad, user.id, _name(user))
            key = store.create_link(squad, user.id, _name(user)).key
            await self.send(str(user.id), cards.link_card(key))
            return
        await self.send(str(update.effective_chat.id), cards.help_card())

    async def cmd_link(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        chat, user = update.effective_chat, update.effective_user
        if chat.type == ChatType.PRIVATE:
            await update.effective_message.reply_text("Send /link inside your study group chat.")
            return
        squad = _squad(chat)
        store.add_member(squad, user.id, _name(user))
        key = store.create_link(squad, user.id, _name(user)).key
        try:
            await self.send(str(user.id), cards.link_card(key))
            await update.effective_message.reply_text(f"🔗 {_name(user)}, I sent your private key in a DM.")
        except Forbidden:  # Telegram bots can't DM someone who never started them
            me = await ctx.bot.get_me()
            button = InlineKeyboardButton("Get my key privately", url=f"https://t.me/{me.username}?start=link_{chat.id}")
            await update.effective_message.reply_text("Tap below, then press Start, to get your private key.",
                                                      reply_markup=InlineKeyboardMarkup([[button]]))

    async def cmd_notes_help(self, update: Update, _ctx):
        await update.effective_message.reply_text(
            "Send a PDF, .txt or .md file to this group with the caption /notes CSE 230 and I'll use it for battles.")

    # buttons, files, messages ---------------------------------------------------------
    async def on_press(self, update: Update, _ctx):
        query = update.callback_query
        try:
            ack = await runner.press(query.data[2:], query.from_user.id, _name(query.from_user), query.message)
        except Exception:  # noqa: BLE001
            log.exception("button failed")
            ack = "Something went wrong 😵"
        try:
            await query.answer(ack[:190] if ack else None)
        except TelegramError:
            pass

    async def on_document(self, update: Update, _ctx):
        msg = update.effective_message
        caption = (msg.caption or "").strip()
        if not caption.lower().startswith("/notes"):
            return
        parts = caption.split(maxsplit=1)          # "/notes CSE 230" or "/notes@SquadBot CSE 230"
        course = parts[1] if len(parts) > 1 else ""
        doc = msg.document
        try:
            data = bytes(await (await doc.get_file()).download_as_bytearray())
        except TelegramError:
            await msg.reply_text("Couldn't download that file. Files over 20 MB can't be read by bots.")
            return
        reply = await runner.add_notes(_squad(update.effective_chat), doc.file_name or "notes.txt", data,
                                       course.strip(), _name(update.effective_user))
        await self._reply(update, reply)

    async def on_message(self, update: Update, _ctx):
        msg, user = update.effective_message, update.effective_user
        if not msg or not user or user.is_bot:
            return
        squad = _squad(update.effective_chat)
        if user.username:
            self.usernames[user.username.lower()] = user.id
        for ent in msg.entities or []:
            target = None
            if ent.type == "text_mention" and ent.user:
                target = ent.user.id
            elif ent.type == "mention":
                target = self.usernames.get(msg.parse_entity(ent).lstrip("@").lower())
            if target and target != user.id:
                link = store.link_for_user(squad.id, target)
                if link:
                    engine.add_mention(store, link, squad, _name(user), msg.text)
        await runner.on_chat_message(squad, user.id, _name(user), msg.text)

    async def start(self):
        await self.app.initialize()
        try:
            await self.app.bot.set_my_commands([BotCommand(n, d) for n, d in COMMANDS])
        except TelegramError:
            log.warning("couldn't set the Telegram command menu")
        await self.app.start()
        await self.app.updater.start_polling(allowed_updates=["message", "callback_query"])
        log.info("Telegram bot online")

    async def stop(self):
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
