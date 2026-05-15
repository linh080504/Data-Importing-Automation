from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Data Import Automation API"
    environment: str = "development"
    debug: bool = False
    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/data_import_automation"
    )
    gemini_api_key: str | None = None
    gemini_api_keys: str | None = None
    gemini_model: str = "gemini-2.0-flash"
    gemini_fallback_models: str | None = None
    n8n_webhook_secret: str | None = None
    n8n_callback_header: str = "X-N8N-Secret"
    internal_webhook_enabled: bool = True

    def gemini_api_keys_list(self) -> list[str]:
        if self.gemini_api_keys:
            return [value.strip() for value in self.gemini_api_keys.split(",") if value.strip()]
        if self.gemini_api_key and self.gemini_api_key.strip():
            return [self.gemini_api_key.strip()]
        return []

    def has_gemini_api_key(self) -> bool:
        return len(self.gemini_api_keys_list()) > 0

    def gemini_models_list(self) -> list[str]:
        primary_model = self.gemini_model.strip() if self.gemini_model and self.gemini_model.strip() else "gemini-2.0-flash"
        fallback_models = []
        if self.gemini_fallback_models:
            fallback_models = [value.strip() for value in self.gemini_fallback_models.split(",") if value.strip()]
        return [primary_model, *fallback_models]

    n8n_allowed_content_type: str = "application/json"
    # Comma-separated browser origins allowed to call the API (needed when Next.js runs on another port).
    # Set to empty to disable CORS middleware entirely.
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://127.0.0.1:3000",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
