"""конфигурация бота: токены, ключи api, пути и настройки по умолчанию.

все секреты берутся из переменных окружения (.env), хардкода нет.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass
class Config:
    # telegram
    bot_token: str = field(default_factory=lambda: os.getenv("BOT_TOKEN", ""))

    # openai / llm
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))
    openai_base_url: str = field(default_factory=lambda: os.getenv("OPENAI_BASE_URL", ""))

    # fatsecret (oauth2 client credentials)
    fatsecret_client_id: str = field(default_factory=lambda: os.getenv("FATSECRET_CLIENT_ID", ""))
    fatsecret_client_secret: str = field(
        default_factory=lambda: os.getenv("FATSECRET_CLIENT_SECRET", "")
    )

    # ocr: "pytesseract" | "easyocr"
    ocr_engine: str = field(default_factory=lambda: os.getenv("OCR_ENGINE", "pytesseract"))

    # база данных
    db_path: str = field(default_factory=lambda: os.getenv("DB_PATH", str(DATA_DIR / "bot.db")))

    # планировщик
    default_tz: str = field(default_factory=lambda: os.getenv("DEFAULT_TZ", "Europe/Moscow"))

    # логирование
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))

    @property
    def ai_enabled(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def fatsecret_enabled(self) -> bool:
        return bool(self.fatsecret_client_id and self.fatsecret_client_secret)

    def validate(self) -> None:
        if not self.bot_token:
            raise RuntimeError(
                "BOT_TOKEN не задан. укажи токен бота в .env (см. .env.example)."
            )


config = Config()
