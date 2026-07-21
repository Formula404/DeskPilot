from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    host: str = Field(default="127.0.0.1", alias="DESKPILOT_HOST")
    port: int = Field(default=8765, alias="DESKPILOT_PORT")
    data_dir: Path = Field(default=Path("data"), alias="DESKPILOT_DATA_DIR")
    cors_origins: list[str] = [
        "http://localhost:1420",
        "http://127.0.0.1:1420",
        "tauri://localhost",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
