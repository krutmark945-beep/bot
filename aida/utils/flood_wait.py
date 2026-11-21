import asyncio
import logging
from aiogram.exceptions import TelegramRetryAfter
from aiogram.types import Message, InlineKeyboardMarkup
from aiogram.methods import SendMessage, SendVideo, SendPhoto
from aiogram.client.bot import Bot

logger = logging.getLogger(__name__)


async def _retry_after_handler(error: TelegramRetryAfter, bot: Bot, method, *args, **kwargs):
    logger.warning("FloodWait: спим %s секунд", error.retry_after)
    await asyncio.sleep(error.retry_after + 1)
    return await method(*args, **kwargs)


async def safe_send_message(bot: Bot, chat_id: int, text: str, **kwargs) -> Message:
    while True:
        try:
            return await bot.send_message(chat_id, text, **kwargs)
        except TelegramRetryAfter as e:
            await _retry_after_handler(e, bot, bot.send_message, chat_id, text, **kwargs)
        except Exception:
            logger.exception("Ошибка отправки сообщения")
            raise


async def safe_send_video(bot: Bot, chat_id: int, video: str, **kwargs) -> Message:
    while True:
        try:
            return await bot.send_video(chat_id, video, **kwargs)
        except TelegramRetryAfter as e:
            await _retry_after_handler(e, bot, bot.send_video, chat_id, video, **kwargs)
        except Exception:
            logger.exception("Ошибка отправки видео")
            raise


async def safe_send_photo(bot: Bot, chat_id: int, photo: str, **kwargs) -> Message:
    while True:
        try:
            return await bot.send_photo(chat_id, photo, **kwargs)
        except TelegramRetryAfter as e:
            await _retry_after_handler(e, bot, bot.send_photo, chat_id, photo, **kwargs)
        except Exception:
            logger.exception("Ошибка отправки фото")
            raise


async def safe_send_media_group(bot: Bot, chat_id: int, media: list, **kwargs) -> list:
    while True:
        try:
            return await bot.send_media_group(chat_id, media, **kwargs)
        except TelegramRetryAfter as e:
            await _retry_after_handler(e, bot, bot.send_media_group, chat_id, media, **kwargs)
        except Exception:
            logger.exception("Ошибка отправки альбома")
            raise


async def safe_edit_message(bot: Bot, chat_id: int, message_id: int, text: str, **kwargs):
    while True:
        try:
            return await bot.edit_message_text(chat_id, message_id, text, **kwargs)
        except TelegramRetryAfter as e:
            await _retry_after_handler(e, bot, bot.edit_message_text, chat_id, message_id, text, **kwargs)
        except Exception:
            logger.exception("Ошибка редактирования сообщения")
            raise