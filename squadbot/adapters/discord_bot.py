"""Discord adapter: renders Cards as embeds, Buttons as components, and forwards commands, presses and messages to
the runner.

Bot setup (discord.com/developers/applications): Bot tab -> turn on MESSAGE CONTENT INTENT, copy the token.
Invite with scopes bot + applications.commands and permissions Send Messages, Read Message History, Embed Links.
"""
from __future__ import annotations

import logging

import discord
from discord import app_commands

from .. import config, engine, runner
from ..cards import COLORS, Button, Card
from ..store import store

log = logging.getLogger("squad.discord")

STYLES = {"primary": discord.ButtonStyle.primary, "secondary": discord.ButtonStyle.secondary,
          "success": discord.ButtonStyle.success, "danger": discord.ButtonStyle.danger}
PRIVATE = {"link"}


def _squad(channel):
    name = f"#{getattr(channel, 'name', 'chat')}"
    guild = getattr(channel, "guild", None)
    if guild:
        name = f"{guild.name} {name}"
    return store.squad("discord", channel.id, name)


def embed(card: Card) -> discord.Embed:
    e = discord.Embed(title=card.title[:256], description=card.body[:4096] or None,
                      color=COLORS.get(card.color, COLORS["info"]))
    for name, value, inline in card.fields[:25]:
        e.add_field(name=name[:256], value=(value or "​")[:1024], inline=inline)
    if card.footer:
        e.set_footer(text=card.footer[:2048])
    return e


async def _on_press(interaction: discord.Interaction, tok: str) -> None:
    await interaction.response.defer()
    ack = await runner.press(tok, interaction.user.id, interaction.user.display_name, interaction.message)
    if ack:
        try:
            await interaction.followup.send(ack, ephemeral=True)
        except discord.HTTPException:
            pass


def view(buttons: list[Button] | None) -> discord.ui.View | None:
    if not buttons:
        return None
    v = discord.ui.View(timeout=None)
    for b in buttons[:25]:
        item = discord.ui.Button(label=b.label[:80], style=STYLES.get(b.style, discord.ButtonStyle.secondary),
                                 custom_id=f"a:{b.token}", row=min(4, b.row))

        async def callback(interaction: discord.Interaction, tok=b.token):
            await _on_press(interaction, tok)

        item.callback = callback
        v.add_item(item)
    return v


class DiscordAdapter:
    platform = "discord"

    def __init__(self, token: str):
        intents = discord.Intents.default()
        intents.message_content = True
        self.token = token
        self.client = discord.Client(intents=intents, activity=discord.Game("/battle · /help"))
        self.tree = app_commands.CommandTree(self.client)
        self._register_commands()
        self.client.event(self.on_ready)
        self.client.event(self.on_message)

    # Adapter interface ------------------------------------------------------
    async def _channel(self, chat_id: str):
        cid = int(chat_id)
        return self.client.get_channel(cid) or await self.client.fetch_channel(cid)

    async def send(self, chat_id: str, card: Card, buttons=None, mentions=None, reply_to=None):
        content = " ".join(f"<@{uid}>" for uid, _ in (mentions or []) if str(uid).isdigit()) or None
        kwargs = {"embed": embed(card), "content": content,
                  "allowed_mentions": discord.AllowedMentions(users=True, roles=False, everyone=False)}
        v = view(buttons)
        if v:
            kwargs["view"] = v
        if reply_to is not None:
            kwargs["reference"] = reply_to
            kwargs["mention_author"] = False
        return await (await self._channel(chat_id)).send(**kwargs)

    async def edit(self, chat_id: str, handle, card=None, buttons=None) -> None:
        kwargs = {}
        if card is not None:
            kwargs["embed"] = embed(card)
        if buttons is not None:
            kwargs["view"] = view(buttons)
        if kwargs:
            await handle.edit(**kwargs)

    # events -------------------------------------------------------------------
    async def on_ready(self):
        if config.DISCORD_GUILD_ID:
            guild = discord.Object(id=int(config.DISCORD_GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()  # global commands can take a while to appear the first time
        log.info("Discord bot online as %s", self.client.user)

    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None or not message.content:
            return
        squad = _squad(message.channel)
        for user in message.mentions:
            link = store.link_for_user(squad.id, user.id)
            if link and user.id != message.author.id:
                engine.add_mention(store, link, squad, message.author.display_name, message.clean_content)
        await runner.on_chat_message(squad, message.author.id, message.author.display_name, message.clean_content)

    # slash commands -----------------------------------------------------------
    async def _run(self, interaction: discord.Interaction, name: str, args: dict | None = None):
        await interaction.response.defer(thinking=True, ephemeral=name in PRIVATE)
        squad = _squad(interaction.channel)
        try:
            reply = await runner.command(squad, name, interaction.user.id, interaction.user.display_name, args)
        except Exception:  # noqa: BLE001
            log.exception("/%s failed", name)
            await interaction.followup.send("Something went wrong 😵 Try again in a moment.", ephemeral=True)
            return
        await self._respond(interaction, reply)

    async def _respond(self, interaction: discord.Interaction, reply: runner.Reply):
        if reply.card is None:
            try:
                await interaction.delete_original_response()
            except discord.HTTPException:
                pass
            return
        kwargs = {"embed": embed(reply.card), "ephemeral": reply.private}
        v = view(reply.buttons)
        if v:
            kwargs["view"] = v
        await interaction.followup.send(**kwargs)

    def _register_commands(self):
        tree, run = self.tree, self._run

        @tree.command(name="battle", description="Boss battle: the squad quizzes together and fights a topic boss")
        @app_commands.describe(topic="What to battle on, e.g. caches", course="Course code, e.g. CSE 230")
        async def battle(interaction: discord.Interaction, topic: str, course: str = ""):
            await run(interaction, "battle", {"topic": topic, "course": course})

        @tree.command(name="lie", description="Two Truths & a Lie: find the false statement")
        @app_commands.describe(topic="What to play on", course="Course code, e.g. CSE 230")
        async def lie(interaction: discord.Interaction, topic: str, course: str = ""):
            await run(interaction, "lie", {"topic": topic, "course": course})

        @tree.command(name="explain", description="Explain It: teach a concept back, the AI grades it")
        @app_commands.describe(topic="What to explain", course="Course code, e.g. CSE 230")
        async def explain(interaction: discord.Interaction, topic: str, course: str = ""):
            await run(interaction, "explain", {"topic": topic, "course": course})

        @tree.command(name="daily", description="Daily Duel: start today's question, or schedule it")
        @app_commands.describe(at="Schedule a daily time like 8pm, or 'off'. Leave empty to play now",
                               topic="Optional topic for today's question")
        async def daily(interaction: discord.Interaction, at: str = "", topic: str = ""):
            await run(interaction, "daily", {"at": at, "topic": topic})

        @tree.command(name="profile", description="Level, XP, badges and streaks")
        @app_commands.describe(user="Whose profile (default: yours)")
        async def profile(interaction: discord.Interaction, user: discord.Member | None = None):
            args = {"target_id": user.id, "target_name": user.display_name} if user else {}
            await run(interaction, "profile", args)

        @tree.command(name="leaderboard", description="Squad XP ranking")
        async def leaderboard(interaction: discord.Interaction):
            await run(interaction, "leaderboard")

        @tree.command(name="insights", description="What the bot knows about this squad's courses")
        async def insights_cmd(interaction: discord.Interaction):
            await run(interaction, "insights")

        @tree.command(name="radar", description="Everything due this week across the squad")
        async def radar(interaction: discord.Interaction):
            await run(interaction, "radar")

        @tree.command(name="plan", description="Pick a study session time together")
        @app_commands.describe(topic="What you'll study", times="Optional: tue 7pm, wed 6pm (default: next 3 evenings)")
        async def plan(interaction: discord.Interaction, topic: str = "", times: str = ""):
            await run(interaction, "plan", {"topic": topic, "times": times})

        @tree.command(name="focus", description="Group Pomodoro: focus together, get pinged at the break")
        @app_commands.describe(minutes="How long (default 25)", topic="What you're working on")
        async def focus(interaction: discord.Interaction, minutes: app_commands.Range[int, 1, 120] = 25,
                        topic: str = ""):
            await run(interaction, "focus", {"minutes": minutes, "topic": topic})

        @tree.command(name="notes", description="Upload lecture notes or slides (PDF, txt, md) for battles")
        @app_commands.describe(file="A PDF, .txt or .md file", course="Course code, e.g. CSE 230")
        async def notes_cmd(interaction: discord.Interaction, file: discord.Attachment, course: str = ""):
            await interaction.response.defer(thinking=True)
            squad = _squad(interaction.channel)
            reply = await runner.add_notes(squad, file.filename, await file.read(), course,
                                           interaction.user.display_name)
            await self._respond(interaction, reply)

        @tree.command(name="ask_cubbie", description="Ask everyone's linked Cubbie for a battle from their Canvas")
        @app_commands.describe(topic="What to battle on", course="Course code, e.g. CSE 230")
        async def ask_cubbie(interaction: discord.Interaction, topic: str, course: str = ""):
            await run(interaction, "ask_cubbie", {"topic": topic, "course": course})

        @tree.command(name="link", description="Get your private key to connect your Cubbie")
        async def link(interaction: discord.Interaction):
            await run(interaction, "link")

        @tree.command(name="quiet", description="Stop reading this channel for study moments")
        async def quiet(interaction: discord.Interaction):
            await run(interaction, "quiet")

        @tree.command(name="watch", description="Let the bot suggest battles when the squad is prepping")
        async def watch(interaction: discord.Interaction):
            await run(interaction, "watch")

        @tree.command(name="help", description="Everything this bot can do")
        async def help_cmd(interaction: discord.Interaction):
            await run(interaction, "help")

    async def start(self):
        await self.client.start(self.token)

    async def stop(self):
        await self.client.close()
