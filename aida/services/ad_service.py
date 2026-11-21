import asyncio
import json
import logging
from datetime import datetime, timedelta

from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, InputMediaPhoto, InputMediaVideo

from database.db import Database
from utils.flood_wait import (
    safe_send_message,
    safe_send_video,
    safe_send_photo,
    safe_send_media_group,
)

logger = logging.getLogger(__name__)


class AdService:
    def __init__(self, db: Database, bot):
        self.db = db
        self.bot = bot
        self._broadcast_task: asyncio.Task | None = None

    # ---------------- интервал ----------------

    async def should_show_ad(self, user_id: int) -> bool:
        """Проверяет, нужно ли показать рекламу пользователю сейчас."""
        user = await self.db.get_user(user_id)
        if not user:
            return False
        if user.get("is_blocked"):
            return False

        interval_hours = int(await self.db.get_setting("ad_interval_hours") or 0)
        interval_minutes = int(await self.db.get_setting("ad_interval_minutes") or 0)

        if interval_hours <= 0 and interval_minutes <= 0:
            return False  # реклама отключена

        last_ad_show = user.get("last_ad_show")
        if not last_ad_show:
            return True  # никогда не показывали рекламу

        last_time = datetime.fromisoformat(last_ad_show)
        interval = timedelta(hours=interval_hours, minutes=interval_minutes)
        return datetime.utcnow() - last_time >= interval

    # ---------------- показ одного поста ----------------

    async def show_ad(self, chat_id: int) -> bool:
        """
        Показывает следующий активный рекламный пост по ротации.
        Возвращает True, если реклама была отправлена.
        """
        active_ads = await self.db.get_active_ads()
        if not active_ads:
            return False

        current_index = int(await self.db.get_setting("current_ad_index") or 0)
        current_index = current_index % len(active_ads)
        ad = active_ads[current_index]

        # Следующий индекс для следующего показа
        await self.db.set_setting("current_ad_index", str(current_index + 1))

        text = ad["text"] or ""
        kb = None
        if ad["button_text"] and ad["button_url"]:
            kb = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text=ad["button_text"], url=ad["button_url"])]
                ]
            )

        try:
            if ad["content_type"] == "album" and ad["media"]:
                await self._send_album(chat_id, ad["media"], text, kb)
            elif ad["content_type"] == "photo" and ad["file_id"]:
                await safe_send_photo(self.bot, chat_id, ad["file_id"], caption=text, reply_markup=kb)
            elif ad["content_type"] == "video" and ad["file_id"]:
                await safe_send_video(self.bot, chat_id, ad["file_id"], caption=text, reply_markup=kb)
            else:
                await safe_send_message(self.bot, chat_id, text, reply_markup=kb)
            return True
        except TelegramForbiddenError:
            # Пользователь заблокировал бота — больше ему не шлём
            logger.info("Пользователь %s заблокировал бота", chat_id)
            await self.db.mark_blocked(chat_id, True)
            return False
        except TelegramRetryAfter as e:
            logger.warning("FloodWait при рассылке: спим %s сек", e.retry_after)
            await asyncio.sleep(e.retry_after + 1)
            return False
        except Exception:
            logger.exception("Не удалось отправить рекламный пост %s пользователю %s", ad["id"], chat_id)
            return False

    async def _send_album(self, chat_id: int, media_json: str, caption: str, kb) -> None:
        """
        Отправляет альбом (несколько фото/видео). Подпись ставится на первый элемент.
        У альбомов Telegram нет inline-кнопок, поэтому кнопку отправляем отдельным сообщением.
        """
        try:
            items = json.loads(media_json)
        except Exception:
            items = []
        if not items:
            return

        media = []
        for index, item in enumerate(items):
            cap = caption if index == 0 else None
            if item.get("type") == "video":
                media.append(InputMediaVideo(media=item["file_id"], caption=cap))
            else:
                media.append(InputMediaPhoto(media=item["file_id"], caption=cap))

        await safe_send_media_group(self.bot, chat_id, media)

        if kb is not None:
            await safe_send_message(self.bot, chat_id, "👇", reply_markup=kb)

    async def record_ad_shown(self, user_id: int) -> None:
        await self.db.update_last_ad_show(user_id)

    # ---------------- фоновая рассылка ----------------

    async def broadcast_once(self) -> int:
        """
        Один проход рассылки: отправляет рекламу всем, кому пора.
        Возвращает количество отправленных сообщений.
        """
        if await self.db.get_setting("broadcast_enabled") != "1":
            return 0

        interval_hours = int(await self.db.get_setting("ad_interval_hours") or 0)
        interval_minutes = int(await self.db.get_setting("ad_interval_minutes") or 0)
        if interval_hours <= 0 and interval_minutes <= 0:
            return 0  # реклама отключена

        active_ads = await self.db.get_active_ads()
        if not active_ads:
            return 0  # нет активной рекламы

        users = await self.db.get_broadcast_users()
        sent = 0
        for user in users:
            uid = user["user_id"]
            try:
                if not await self.should_show_ad(uid):
                    continue
                ok = await self.show_ad(uid)
                if ok:
                    await self.record_ad_shown(uid)
                    sent += 1
                    # Пауза между отправками, чтобы не словить FloodWait
                    await asyncio.sleep(0.1)
            except Exception:
                logger.exception("Ошибка рассылки пользователю %s", uid)
        if sent:
            logger.info("Рассылка рекламы: отправлено %d сообщений", sent)
        return sent

    async def broadcast_loop(self) -> None:
        """Бесконечный цикл фоновой рассылки."""
        logger.info("Фоновая рассылка рекламы запущена")
        while True:
            try:
                check_seconds = int(await self.db.get_setting("broadcast_check_seconds") or 60)
                if check_seconds < 10:
                    check_seconds = 10
                await self.broadcast_once()
            except asyncio.CancelledError:
                logger.info("Фоновая рассылка остановлена")
                raise
            except Exception:
                logger.exception("Ошибка в цикле фоновой рассылки")
                check_seconds = 60
            await asyncio.sleep(check_seconds)

    def start_broadcast(self) -> None:
        if self._broadcast_task is None or self._broadcast_task.done():
            self._broadcast_task = asyncio.create_task(self.broadcast_loop())

    async def stop_broadcast(self) -> None:
        if self._broadcast_task and not self._broadcast_task.done():
            self._broadcast_task.cancel()
            try:
                await self._broadcast_task
            except asyncio.CancelledError:
                pass
