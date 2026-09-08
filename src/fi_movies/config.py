from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str = "postgresql+psycopg://fi_movies:fi_movies@localhost:5432/fi_movies"
    scrape_interval_seconds: int = Field(default=1800, ge=60)
    nytleffaan_base_url: str = "https://nytleffaan.fi"
    nytleffaan_start_city: str = "helsinki"
    kinoregina_base_url: str = "https://kinoregina.fi"
    kinoregina_enabled: bool = True
    korjaamo_base_url: str = "https://korjaamokino.fi"
    korjaamo_enabled: bool = True
    riviera_base_url: str = "https://www.rivieracinemas.fi"
    riviera_enabled: bool = True
    tmdb_api_key: str | None = None
    tmdb_read_access_token: str | None = None
    tmdb_read_access_token_file: str = "/run/secrets/tmdb_token"
    tmdb_language: str = "en-US"

    @property
    def resolved_tmdb_read_access_token(self) -> str | None:
        if self.tmdb_read_access_token:
            return self.tmdb_read_access_token
        for path in (Path(self.tmdb_read_access_token_file), Path("TOKEN")):
            try:
                token = path.read_text(encoding="utf-8").strip()
            except OSError:
                continue
            if token:
                return token
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
