from dataclasses import dataclass
import os
from dotenv import load_dotenv

load_dotenv()

def _req(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required env var: {name}")
    return v

@dataclass(frozen=True)
class Settings:
    bot_token: str
    supabase_url: str
    supabase_service_key: str
    env: str
    log_level: str

def get_settings() -> Settings:
    return Settings(
        bot_token=_req("BOT_TOKEN"),
        supabase_url=_req("SUPABASE_URL"),
        supabase_service_key=_req("SUPABASE_SERVICE_KEY"),
        env=os.getenv("ENV", "dev"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )