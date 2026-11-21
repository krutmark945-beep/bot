import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS
from database.db import Database
from services.ad_service import AdService
from keyboards.user_kb import get_main_kb, get_back_kb
from keyboards.inline_kb import get_series_selection_kb

logger = logging.getLogger(__name__)

router = Router()


class VideoStates(StatesGroup):
    waiting_series = State()


def register_handlers(dp, db: Database, ad_service: AdService):
    dp.include_router(router)

    # Сохраняем ссылки в ф storage для доступа из хендлеров
    router.db = db
    router.ad_service = ad_service


# ---------------- пользовательские хендлеры ----------------

@router.message(CommandStart())
async def cmd_start(message: Message):
    db: Database = message.bot.db  # type: ignore
    await db.add_user(
        message.from_user.id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name,
    )
    await message.answer(
        "👋 Добро пожаловать!\n\n"
        "Я бот для выдачи видеосерий. Выберите действие ниже:",
        reply_markup=get_main_kb(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message):
    await message.answer("Главное меню:", reply_markup=get_main_kb())


@router.message(F.text == "🔙 Назад")
async def back_to_main(message: Message):
    from config import ADMIN_IDS
    from keyboards.admin_kb import get_admin_main_kb

    # Если админ вышел из подменю — возвращаем в админ-панель
    if message.from_user and message.from_user.id in ADMIN_IDS:
        await message.answer("Админ-панель:", reply_markup=get_admin_main_kb())
        return
    await message.answer("Главное меню:", reply_markup=get_main_kb())


@router.message(F.text == "ℹ️ Помощь")
async def cmd_help(message: Message):
    await message.answer(
        "📖 <b>Помощь</b>\n\n"
        "• Нажмите «🎬 Серии», чтобы выбрать и посмотреть серию.\n"
        "• Перед просмотром нужно быть подписанным на канал.\n\n"
        "Если у вас вопросы — обратитесь к администратору.",
    )


@router.message(F.text == "📋 Моя подписка")
async def check_my_subscription(message: Message):
    from config import REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_URL
    from aiogram.enums import ChatMemberStatus

    bot = message.bot
    try:
        member = await bot.get_chat_member(REQUIRED_CHANNEL_ID, message.from_user.id)
        if member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
            await message.answer("✅ Вы подписаны на канал. Доступ к сериям открыт.")
        else:
            from keyboards.inline_kb import get_subscription_kb
            await message.answer(
                "❌ Вы не подписаны на канал.",
                reply_markup=get_subscription_kb(REQUIRED_CHANNEL_URL),
            )
    except Exception:
        logger.exception("Ошибка проверки подписки")
        await message.answer("Не удалось проверить подписку. Попробуйте позже.")


@router.message(F.text == "🎬 Серии")
async def show_series(message: Message, state: FSMContext):
    from config import ADMIN_IDS, REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_URL
    from aiogram.enums import ChatMemberStatus
    from keyboards.inline_kb import get_subscription_kb
    from keyboards.admin_kb import get_series_admin_kb

    db: Database = message.bot.db  # type: ignore

    # Админ-панель: админ видит меню управления сериями
    if message.from_user and message.from_user.id in ADMIN_IDS:
        await state.clear()
        await message.answer("Управление сериями:", reply_markup=get_series_admin_kb())
        return

    # Обычный пользователь: проверка подписки
    try:
        member = await message.bot.get_chat_member(REQUIRED_CHANNEL_ID, message.from_user.id)
        if member.status not in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
            await message.answer(
                "⛔ Для просмотра серий нужно подписаться на канал.",
                reply_markup=get_subscription_kb(REQUIRED_CHANNEL_URL),
            )
            return
    except Exception:
        logger.exception("Ошибка проверки подписки")
        await message.answer("Не удалось проверить подписку. Попробуйте позже.")
        return

    series_list = await db.get_all_series()
    if not series_list:
        await message.answer("Серии пока не добавлены. Обратитесь к администратору.")
        return

    await state.set_state(VideoStates.waiting_series)
    await message.answer(
        "📺 Выберите серию:",
        reply_markup=get_series_selection_kb(series_list, page=0),
    )


@router.callback_query(F.data.startswith("series_page:"))
async def series_pagination(callback: CallbackQuery, state: FSMContext):
    db: Database = callback.bot.db  # type: ignore
    page = int(callback.data.split(":")[1])
    series_list = await db.get_all_series()
    await callback.message.edit_text(
        "📺 Выберите серию:",
        reply_markup=get_series_selection_kb(series_list, page=page),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("watch:"))
async def watch_series(callback: CallbackQuery, state: FSMContext):
    db: Database = callback.bot.db  # type: ignore
    ad_service: AdService = callback.bot.ad_service  # type: ignore

    series_id = int(callback.data.split(":")[1])
    series = await db.get_series(series_id)
    if not series:
        await callback.answer("Серия не найдена", show_alert=True)
        return

    user_id = callback.from_user.id

    # Проверка подписки
    from config import REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_URL
    from aiogram.enums import ChatMemberStatus
    from keyboards.inline_kb import get_subscription_kb

    try:
        member = await callback.bot.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
        if member.status not in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
            await callback.message.answer(
                "⛔ Сначала подпишитесь на канал.",
                reply_markup=get_subscription_kb(REQUIRED_CHANNEL_URL),
            )
            await callback.answer()
            return
    except Exception:
        logger.exception("Ошибка проверки подписки")
        await callback.answer("Не удалось проверить подписку", show_alert=True)
        return

    # Показ рекламы по интервалу
    if await ad_service.should_show_ad(user_id):
        showed = await ad_service.show_ad(user_id)
        if showed:
            await ad_service.record_ad_shown(user_id)

    # Отправка видео
    try:
        caption = f"🎬 {series['title']} (Серия #{series['series_number']})"
        await callback.bot.send_video(
            chat_id=user_id,
            video=series["file_id"],
            caption=caption,
        )
        await callback.answer()
    except Exception:
        logger.exception("Ошибка отправки видео %s", series_id)
        await callback.answer("Ошибка при отправке видео", show_alert=True)


@router.callback_query(F.data == "main_menu")
async def main_menu_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("Главное меню:", reply_markup=get_main_kb())
    await callback.answer()


@router.callback_query(F.data == "check_subscription")
async def check_subscription_cb(callback: CallbackQuery, state: FSMContext):
    """Проверка подписки по нажатию кнопки «Проверить подписку»."""
    from config import REQUIRED_CHANNEL_ID, REQUIRED_CHANNEL_URL
    from aiogram.enums import ChatMemberStatus
    from keyboards.inline_kb import get_subscription_kb

    db: Database = callback.bot.db  # type: ignore
    user_id = callback.from_user.id

    try:
        member = await callback.bot.get_chat_member(REQUIRED_CHANNEL_ID, user_id)
        if member.status in {ChatMemberStatus.MEMBER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR}:
            # Добавляем пользователя в БД, если ещё не добавлен
            await db.add_user(
                user_id,
                callback.from_user.username,
                callback.from_user.first_name,
                callback.from_user.last_name,
            )
            try:
                await callback.message.delete()
            except Exception:
                pass
            await callback.message.answer(
                "✅ Спасибо за подписку! Доступ к сериям открыт.",
                reply_markup=get_main_kb(),
            )
            try:
                await callback.answer("Подписка подтверждена")
            except Exception:
                pass
        else:
            await callback.answer("Вы ещё не подписаны на канал", show_alert=True)
    except Exception:
        logger.exception("Ошибка проверки подписки")
        await callback.answer("Не удалось проверить подписку. Попробуйте позже.", show_alert=True)