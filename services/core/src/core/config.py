from functools import lru_cache

from fastapi import Request
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HUB_", env_file=".env", extra="ignore")

    environment: str = "development"
    public_url: str = "http://localhost:8080"
    # "hello=http://app-hello:8000,files=http://app-files:8000"
    apps: str = ""
    app_timeout_seconds: float = Field(default=2.0, gt=0)

    # --- Database -------------------------------------------------------------------
    # postgresql+asyncpg://gebruiker:wachtwoord@host:5432/database. Leeg: core draait
    # zonder database (alleen standaardthema en app-status; inloggen werkt dan niet).
    database_url: str = ""
    # Migraties uitvoeren bij het starten (beveiligd met een advisory lock, dus veilig
    # met meerdere replica's).
    auto_migrate: bool = True
    database_connect_timeout_seconds: float = Field(default=30.0, ge=0)

    # --- Klanten (tenants) ----------------------------------------------------------
    # Klanten worden herkend aan het subdomein: <klant>.<base_domain>.
    # Ontwikkelen: "localhost" (browsers sturen acme.localhost naar 127.0.0.1).
    base_domain: str = "localhost"
    # Mogen nieuwe klanten zichzelf aanmelden via POST /signup?
    allow_signup: bool = False

    # --- Inloggen -------------------------------------------------------------------
    # Ed25519-privésleutel (PEM) voor het ondertekenen van tokens. Verplicht in
    # productie (alle replica's moeten dezelfde sleutel gebruiken); in ontwikkeling
    # wordt anders een tijdelijke sleutel gemaakt.
    jwt_private_key: str = ""
    jwt_private_key_file: str = ""
    access_token_minutes: int = Field(default=15, ge=1, le=120)
    refresh_token_days: int = Field(default=30, ge=1, le=365)
    # Secure-vlag op de refresh-cookie; alleen uitzetten voor http://localhost.
    cookie_secure: bool = True

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

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
def load_settings() -> Settings:
    """Instellingen uit de omgeving (één keer gelezen)."""
    return Settings()


def get_settings(request: Request) -> Settings:
    """FastAPI-afhankelijkheid: de instellingen waarmee de app is gemaakt."""
    return request.app.state.settings
