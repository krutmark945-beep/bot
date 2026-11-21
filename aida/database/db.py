import aiosqlite
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

from config import DB_PATH

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path

    def _ensure_dir(self) -> None:
        directory = os.path.dirname(self.db_path)
        if directory and not os.path.exists(directory):
            os.makedirs(directory, exist_ok=True)

    @asynccontextmanager
    async def _connect(self):
        self._ensure_dir()
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            yield conn

    async def init(self) -> None:
        async with self._connect() as conn:
            await conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id       INTEGER PRIMARY KEY,
                    username      TEXT,
                    first_name    TEXT,
                    last_name     TEXT,
                    joined_at     TEXT NOT NULL,
                    last_ad_show  TEXT,
                    is_banned     INTEGER DEFAULT 0,
                    is_blocked    INTEGER DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS series (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    title           TEXT NOT NULL,
                    series_number   INTEGER NOT NULL,
                    file_id         TEXT NOT NULL,
                    file_unique_id  TEXT,
                    storage_message_id INTEGER,
                    created_at      TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ads (
                    id            INTEGER PRIMARY KEY AUTOINCREMENT,
                    content_type  TEXT NOT NULL DEFAULT 'text',
                    text          TEXT,
                    file_id       TEXT,
                    media         TEXT,
                    button_text   TEXT,
                    button_url    TEXT,
                    is_active     INTEGER DEFAULT 1,
                    created_at    TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS settings (
                    key   TEXT PRIMARY KEY,
                    value TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_series_number ON series(series_number);
                CREATE INDEX IF NOT EXISTS idx_ads_active ON ads(is_active);
                """
            )
            # Миграция: добавляем столбцы, если их ещё нет (старая БД)
            try:
                await conn.execute(
                    "ALTER TABLE users ADD COLUMN is_blocked INTEGER DEFAULT 0"
                )
            except Exception:
                pass
            try:
                await conn.execute("ALTER TABLE ads ADD COLUMN media TEXT")
            except Exception:
                pass
            # Настройки по умолчанию (если их ещё нет)
            defaults = {
                "ad_interval_hours": "1",
                "ad_interval_minutes": "0",
                "broadcast_enabled": "1",
                "broadcast_check_seconds": "60",
                "current_ad_index": "0",
            }
            for key, value in defaults.items():
                await conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)",
                    (key, value),
                )
            await conn.commit()
        logger.info("База данных инициализирована: %s", self.db_path)

    # ---------------- users ----------------

    async def add_user(self, user_id: int, username: str | None, first_name: str | None, last_name: str | None) -> None:
        now = datetime.utcnow().isoformat()
        async with self._connect() as conn:
            await conn.execute(
                """
                INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, joined_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, username, first_name, last_name, now),
            )
            await conn.commit()

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        async with self._connect() as conn:
            async with conn.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def update_last_ad_show(self, user_id: int) -> None:
        now = datetime.utcnow().isoformat()
        async with self._connect() as conn:
            await conn.execute(
                "UPDATE users SET last_ad_show = ? WHERE user_id = ?",
                (now, user_id),
            )
            await conn.commit()

    async def get_all_users(self) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            async with conn.execute("SELECT * FROM users ORDER BY user_id") as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def get_broadcast_users(self) -> list[dict[str, Any]]:
        """Пользователи, которым можно рассылать (не забанены и не заблокировали бота)."""
        async with self._connect() as conn:
            async with conn.execute(
                "SELECT * FROM users WHERE is_banned = 0 AND is_blocked = 0 ORDER BY user_id"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def mark_blocked(self, user_id: int, blocked: bool = True) -> None:
        async with self._connect() as conn:
            await conn.execute(
                "UPDATE users SET is_blocked = ? WHERE user_id = ?",
                (1 if blocked else 0, user_id),
            )
            await conn.commit()

    async def ban_user(self, user_id: int, banned: bool = True) -> None:
        async with self._connect() as conn:
            await conn.execute(
                "UPDATE users SET is_banned = ? WHERE user_id = ?",
                (1 if banned else 0, user_id),
            )
            await conn.commit()

    # ---------------- series ----------------

    async def add_series(
        self,
        title: str,
        series_number: int,
        file_id: str,
        file_unique_id: str | None = None,
        storage_message_id: int | None = None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO series (title, series_number, file_id, file_unique_id, storage_message_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (title, series_number, file_id, file_unique_id, storage_message_id, now),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_series(self, series_id: int) -> dict[str, Any] | None:
        async with self._connect() as conn:
            async with conn.execute(
                "SELECT * FROM series WHERE id = ?", (series_id,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_series_by_number(self, series_number: int) -> dict[str, Any] | None:
        async with self._connect() as conn:
            async with conn.execute(
                "SELECT * FROM series WHERE series_number = ?", (series_number,)
            ) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_all_series(self) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            async with conn.execute(
                "SELECT * FROM series ORDER BY series_number"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def delete_series(self, series_id: int) -> bool:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "DELETE FROM series WHERE id = ?", (series_id,)
            )
            await conn.commit()
            return cursor.rowcount > 0

    # ---------------- ads ----------------

    async def add_ad(
        self,
        content_type: str,
        text: str | None,
        file_id: str | None,
        button_text: str | None,
        button_url: str | None,
        is_active: bool = True,
        media: str | None = None,
    ) -> int:
        now = datetime.utcnow().isoformat()
        async with self._connect() as conn:
            cursor = await conn.execute(
                """
                INSERT INTO ads (content_type, text, file_id, media, button_text, button_url, is_active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (content_type, text, file_id, media, button_text, button_url, int(is_active), now),
            )
            await conn.commit()
            return cursor.lastrowid

    async def get_ad(self, ad_id: int) -> dict[str, Any] | None:
        async with self._connect() as conn:
            async with conn.execute("SELECT * FROM ads WHERE id = ?", (ad_id,)) as cur:
                row = await cur.fetchone()
                return dict(row) if row else None

    async def get_all_ads(self) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            async with conn.execute(
                "SELECT * FROM ads ORDER BY id DESC"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def get_active_ads(self) -> list[dict[str, Any]]:
        async with self._connect() as conn:
            async with conn.execute(
                "SELECT * FROM ads WHERE is_active = 1 ORDER BY id"
            ) as cur:
                return [dict(r) for r in await cur.fetchall()]

    async def set_ad_active(self, ad_id: int, active: bool) -> bool:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "UPDATE ads SET is_active = ? WHERE id = ?",
                (1 if active else 0, ad_id),
            )
            await conn.commit()
            return cursor.rowcount > 0

    async def delete_ad(self, ad_id: int) -> bool:
        async with self._connect() as conn:
            cursor = await conn.execute("DELETE FROM ads WHERE id = ?", (ad_id,))
            await conn.commit()
            return cursor.rowcount > 0

    # ---------------- settings ----------------

    async def get_setting(self, key: str) -> str | None:
        async with self._connect() as conn:
            async with conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ) as cur:
                row = await cur.fetchone()
                return row["value"] if row else None

    async def set_setting(self, key: str, value: str) -> None:
        async with self._connect() as conn:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            await conn.commit()

    async def delete_setting(self, key: str) -> bool:
        async with self._connect() as conn:
            cursor = await conn.execute(
                "DELETE FROM settings WHERE key = ?", (key,)
            )
            await conn.commit()
            return cursor.rowcount > 0