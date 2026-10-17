import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def setting(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


DATABASE_PATH = setting("DATABASE_PATH", str(ROOT / "data" / "finance.db"))
DEMO_MODE = setting("DEMO_MODE", "true").lower() == "true"
FRONTEND_ORIGIN = setting("FRONTEND_ORIGIN", "http://localhost:5173")
PUBLIC_BASE_URL = setting("PUBLIC_BASE_URL").rstrip("/")

OPENAI_API_KEY = setting("OPENAI_API_KEY")
OPENAI_TRANSCRIPTION_MODEL = setting(
    "OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe"
)
OPENAI_EXTRACTION_MODEL = setting("OPENAI_EXTRACTION_MODEL", "gpt-4o-mini")
LOCAL_WHISPER_MODEL = setting("LOCAL_WHISPER_MODEL", "base")
KOKORO_MODEL_DIR = Path(setting(
    "KOKORO_MODEL_DIR", str(ROOT / "backend" / "data" / "kokoro")
))

WHATSAPP_ACCESS_TOKEN = setting("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = setting("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = setting("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_APP_SECRET = setting("WHATSAPP_APP_SECRET")
WHATSAPP_GRAPH_API_VERSION = setting("WHATSAPP_GRAPH_API_VERSION", "v23.0")
RETELL_FUNCTION_SECRET = setting("RETELL_FUNCTION_SECRET")
RETELL_API_KEY = setting("RETELL_API_KEY")
RETELL_PUBLIC_KEY = setting("RETELL_PUBLIC_KEY")
RETELL_AGENT_ID = setting("RETELL_AGENT_ID")
RETELL_PHONE_NUMBER = setting("RETELL_PHONE_NUMBER")
AUTHORIZED_PHONE_NUMBERS = {
    "".join(character for character in number if character.isdigit())
    for number in setting("AUTHORIZED_PHONE_NUMBERS").split(",")
    if any(character.isdigit() for character in number)
}
