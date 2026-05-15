from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/fb_scraper"
    fb_profile_dir: str = "./runtime/fb-profile"
    headless: bool = False
    scrape_interval_minutes: int = 240
    max_posts_per_group: int = 20
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    log_level: str = "INFO"
    openai_api_key: str = ""
    ai_model: str = "gpt-5.4-nano"
    max_concurrent_groups: int = 5
    max_scrolls: int = 15

    @field_validator("fb_profile_dir")
    @classmethod
    def resolve_profile_dir(cls, v: str) -> str:
        return str(Path(v).resolve())


def load_groups_config(path: str = "config/groups.yaml") -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("groups", [])


def load_criteria_config(path: str = "config/criteria.yaml") -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


settings = Settings()
