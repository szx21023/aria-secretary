from functools import lru_cache

from anthropic import AsyncAnthropic

from app.config import get_settings

MODEL = "claude-opus-4-8"


@lru_cache
def get_client() -> AsyncAnthropic:
    settings = get_settings()
    return AsyncAnthropic(api_key=settings.anthropic_api_key)
