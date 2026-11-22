import os
from dotenv import load_dotenv

load_dotenv()


def _get_env(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None:
        raise RuntimeError(f"Переменная окружения {name} не задана")
    return value


BOT_TOKEN: str = _get_env("BOT_TOKEN")

ADMIN_IDS: list[int] = [
    int(x.strip()) for x in _get_env("ADMIN_IDS").split(",") if x.strip()
]

REQUIRED_CHANNEL_ID: int = int(_get_env("REQUIRED_CHANNEL_ID"))
REQUIRED_CHANNEL_URL: str = _get_env("REQUIRED_CHANNEL_URL")
STORAGE_CHANNEL_ID: int = int(_get_env("STORAGE_CHANNEL_ID"))

DB_PATH: str = _get_env("DB_PATH", "database/bot.db")

# Где хранятся видео: 'storage' (пересылка из канала-хранилища) или 'direct' (прямой file_id)
VIDEO_SOURCE: str = _get_env("VIDEO_SOURCE", "direct")

# Настройка логирования
LOG_LEVEL: str = _get_env("LOG_LEVEL", "INFO")