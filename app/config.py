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
    supabase_key: str
    env: str
    log_level: str


def _get_supabase_key() -> str:
    """Backward-compatible env lookup for Supabase service key."""
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    if service_key:
        return service_key
    return _req("SUPABASE_KEY")

def get_settings() -> Settings:
    return Settings(
        bot_token=_req("BOT_TOKEN"),
        supabase_url=_req("SUPABASE_URL"),
        supabase_key=_get_supabase_key(),
        env=os.getenv("ENV", "dev"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
