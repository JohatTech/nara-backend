from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_backend_dir = Path(__file__).resolve().parent.parent.parent
_env_files = [str(_backend_dir / ".env"), ".env"]


class Settings(BaseSettings):
    supabase_url: str
    supabase_publishable_key: str = Field(
        validation_alias=AliasChoices(
            "SUPABASE_PUBLISHABLE_KEY",
            "supabase_publishable_key",
            "SUPABASE_ANON_KEY",
            "supabase_anon_key",
        )
    )
    supabase_secret_key: str = Field(
        validation_alias=AliasChoices(
            "SUPABASE_SECRET_KEY",
            "supabase_secret_key",
            "SUPABASE_SERVICE_ROLE_KEY",
            "supabase_service_role_key",
        )
    )
    supabase_jwks_url: str = Field(
        default="",
        validation_alias=AliasChoices(
            "SUPABASE_JWKS_URL",
            "supabase_jwks_url",
        ),
    )
    environment: str = "development"
    cors_origins: str = "https://nara-frontend-six.vercel.app,http://localhost:3001,http://127.0.0.1:3001,http://localhost:8080,http://127.0.0.1:8080,http://localhost:8000,http://127.0.0.1:8000,http://localhost:8081,http://127.0.0.1:8081"
    google_calendar_id: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_CALENDAR_ID", "google_calendar_id"),
    )
    google_calendar_timezone: str = Field(
        default="America/Bogota",
        validation_alias=AliasChoices("GOOGLE_CALENDAR_TIMEZONE", "google_calendar_timezone"),
    )
    google_calendar_embed_url: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_CALENDAR_EMBED_URL", "google_calendar_embed_url"),
    )
    google_service_account_json: str = Field(
        default="",
        validation_alias=AliasChoices("GOOGLE_SERVICE_ACCOUNT_JSON", "google_service_account_json"),
    )
    shared_owner_id: str = Field(
        default="",
        validation_alias=AliasChoices("SHARED_OWNER_ID", "shared_owner_id"),
    )
    model_config = SettingsConfigDict(env_file=_env_files, env_file_encoding="utf-8", extra="ignore")

    def model_post_init(self, __context: object) -> None:
        if not self.supabase_jwks_url and self.supabase_url:
            self.supabase_jwks_url = f"{self.supabase_url.rstrip('/')}/auth/v1/.well-known/jwks.json"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    # Backward compatibility properties
    @property
    def supabase_anon_key(self) -> str:
        return self.supabase_publishable_key

    @property
    def supabase_service_role_key(self) -> str:
        return self.supabase_secret_key


settings = Settings()
