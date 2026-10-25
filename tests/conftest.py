"""Shared test setup: offline AI, tiny timers, a throwaway data folder and a fake chat app."""
import os
import tempfile

os.environ.update(
    DATA_DIR=tempfile.mkdtemp(), LLM_PROVIDER="fake", QUESTION_SECONDS="2", LIE_SECONDS="2", WAGER_SECONDS="0.4",
    EXPLAIN_SECONDS="1.5", OPEN_FLOOR_SECONDS="1.5", INTRO_PAUSE="0", REVEAL_PAUSE="0", DAILY_NOW_SECONDS="2",
    DAILY_SECONDS="2", EXPLAIN_ROUNDS="2", NUDGE_COOLDOWN_MINUTES="30",
)


class FakeAdapter:
    """Records everything the bot sends. `on_send(adapter, card, buttons)` can press buttons like a player would."""

    def __init__(self, platform, on_send=None):
        self.platform, self.on_send = platform, on_send
        self.sent, self.edits, self.n = [], [], 0

    async def send(self, chat_id, card, buttons=None, mentions=None, reply_to=None):
        self.n += 1
        self.sent.append({"card": card, "buttons": buttons or [], "mentions": mentions or [], "handle": self.n})
        if self.on_send:
            await self.on_send(self, card, buttons or [])
        return self.n

    async def edit(self, chat_id, handle, card=None, buttons=None):
        self.edits.append({"handle": handle, "card": card, "buttons": buttons})

    def titles(self):
        return [s["card"].title for s in self.sent]

    def find(self, prefix):
        return [s for s in self.sent if s["card"].title.startswith(prefix)]
