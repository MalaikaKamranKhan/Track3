"""Settings, all from environment variables (see .env.example)."""
import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader so teammates don't need python-dotenv."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(Path(__file__).resolve().parent.parent / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def num(name: str, default: float) -> float:
    try:
        return float(env(name, str(default)))
    except ValueError:
        return default


BOT_NAME = env("BOT_NAME", "Squad")
IMAGES = env("IMAGES", "on").lower() not in {"0", "off", "false", "no"}  # picture cards (boss, podium, profile)
PUBLIC_URL = env("PUBLIC_URL", "http://localhost:8000").rstrip("/")
PORT = int(num("PORT", 8000))
DATA_DIR = Path(env("DATA_DIR", str(Path(__file__).resolve().parent.parent / "data")))

DISCORD_TOKEN = env("DISCORD_TOKEN")
DISCORD_GUILD_ID = env("DISCORD_GUILD_ID")  # optional: instant slash-command sync for one server
TELEGRAM_TOKEN = env("TELEGRAM_TOKEN")

# LLM: fake | gemini | anthropic | openai | bedrock
LLM_PROVIDER = env("LLM_PROVIDER", "fake").lower()
LLM_MODEL = env("LLM_MODEL")
GEMINI_API_KEY = env("GEMINI_API_KEY")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
OPENAI_API_KEY = env("OPENAI_API_KEY")
AWS_REGION = env("AWS_REGION", "us-east-1")

# Games
QUESTIONS_PER_BATTLE = int(num("QUESTIONS_PER_BATTLE", 5))
QUESTION_SECONDS = int(num("QUESTION_SECONDS", 25))
LIE_SECONDS = int(num("LIE_SECONDS", 30))
WAGER_SECONDS = num("WAGER_SECONDS", 12)
EXPLAIN_ROUNDS = int(num("EXPLAIN_ROUNDS", 3))
EXPLAIN_SECONDS = num("EXPLAIN_SECONDS", 75)
OPEN_FLOOR_SECONDS = num("OPEN_FLOOR_SECONDS", 45)
DAILY_SECONDS = int(num("DAILY_SECONDS", 1800))        # how long a scheduled Daily Duel stays open
DAILY_NOW_SECONDS = int(num("DAILY_NOW_SECONDS", 90))  # /daily started by hand
INTRO_PAUSE = num("INTRO_PAUSE", 2)
REVEAL_PAUSE = num("REVEAL_PAUSE", 3)
NUDGE_COOLDOWN_MINUTES = num("NUDGE_COOLDOWN_MINUTES", 30)
SCHEDULER_SECONDS = num("SCHEDULER_SECONDS", 30)
