from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HUB_", env_file=".env", extra="ignore")

    # Interne adres van de core (apps, tokens, auditlog).
    core_url: str = "http://core:8000"
    # Conversaties (24 uur). Leeg = in geheugen (alleen ontwikkeling/1 replica).
    redis_url: str = ""
    conversation_ttl_seconds: int = 24 * 3600

    # LLM (Claude via de Anthropic API). Zonder sleutel staat de assistent uit.
    anthropic_api_key: str = Field(
        default="", validation_alias=AliasChoices("ANTHROPIC_API_KEY", "HUB_ANTHROPIC_API_KEY")
    )
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = Field(default="medium", pattern="^(low|medium|high|xhigh|max)$")
    llm_max_tokens: int = Field(default=16000, ge=1024, le=64000)
    # Maximaal aantal model-stappen per beurt (beveiliging tegen eindeloze lussen).
    max_steps: int = Field(default=8, ge=1, le=30)
    tool_timeout_seconds: float = 20.0
    max_tool_result_chars: int = 16000

    @property
    def enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def load_settings() -> Settings:
    return Settings()
