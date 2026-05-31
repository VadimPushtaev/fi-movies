from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    database_url: str = "postgresql+psycopg://fi_movies:fi_movies@localhost:5432/fi_movies"
    scrape_interval_seconds: int = Field(default=1800, ge=60)
    nytleffaan_base_url: str = "https://nytleffaan.fi"
    nytleffaan_start_city: str = "helsinki"


@lru_cache
def get_settings() -> Settings:
    return Settings()

