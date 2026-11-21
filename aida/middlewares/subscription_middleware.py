import logging
from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery
from aiogram.enums import ChatMemberStatus

from config import REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_URL, ADMIN_IDS
from utils.flood_wait import safe_send_message

logger = logging.getLogger(__name__)

SUBSCRIBED_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}


class SubscriptionMiddleware(BaseMiddleware):
    """
    Проверяет подписку пользователя на обязательный канал.
    Если не подписан — отправляет сообщение с кнопкой-ссылкой и кнопкой «Проверить подписку»,
    и прерывает дальнейшую обработку (handler не вызывается).
    """

    async def __call__(self, handler, event, data):
        # Получаем user_id из события
        user_id = None
        if isinstance(event, Message):
            user_id = event.from_user.id if event.from_user else None
        elif isinstance(event, CallbackQuery):
            user_id = event.from_user.id if event.from_user else None

        if user_id is None:
            return await handler(event, data)

        # Админы проходят без проверки подписки (иначе не смогут загружать серии)
        if user_id in ADMIN_IDS:
            return await handler(event, data)

        # Кнопка «Проверить подписку» должна всегда доходить до хендлера,
        # иначе получится зацикливание
        if isinstance(event, CallbackQuery) and event.data == "check_subscription":
            return await handler(event, data)

        bot = data["bot"]

        try:
            member = await bot.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
            if member.status in SUBSCRIBED_STATUSES:
                return await handler(event, data)
        except Exception as exc:
            # Бот не админ в канале или канал недоступен — проверка невозможна.
            # Не блокируем пользователей и не спамим ошибками в логи.
            logger.debug("Проверка подписки недоступна для %s: %s", user_id, exc)
            return await handler(event, data)

        # Не подписан — блокируем
        from keyboards.inline_kb import get_subscription_kb

        text = (
            "⛔ <b>Доступ ограничен</b>\n\n"
            "Для использования бота необходимо подписаться на наш канал.\n"
            "После подписки нажмите кнопку «Проверить подписку»."
        )
        kb = get_subscription_kb(REQUIRED_CHANNEL_URL)

        if isinstance(event, Message):
            await safe_send_message(bot, event.chat.id, text, reply_markup=kb)
        elif isinstance(event, CallbackQuery):
            await safe_send_message(bot, event.message.chat.id, text, reply_markup=kb)
            try:
                await event.answer("Требуется подписка на канал", show_alert=True)
            except Exception:
                pass
        return