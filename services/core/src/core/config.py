from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HUB_", env_file=".env", extra="ignore")

    environment: str = "development"
    public_url: str = "http://localhost:8080"
    # "hello=http://app-hello:8000,files=http://app-files:8000"
    apps: str = ""
    app_timeout_seconds: float = Field(default=2.0, gt=0)

    def app_urls(self) -> dict[str, str]:
        """Zet ``HUB_APPS`` om naar ``{app_id: interne_url}``."""
        result: dict[str, str] = {}
        for item in self.apps.split(","):
            item = item.strip()
            if not item:
                continue
            app_id, sep, url = item.partition("=")
            if not sep or not app_id.strip() or not url.strip():
                raise ValueError(f"Ongeldige HUB_APPS-regel: {item!r} (verwacht id=url)")
            result[app_id.strip()] = url.strip().rstrip("/")
        return result


@lru_cache
def get_settings() -> Settings:
    return Settings()
