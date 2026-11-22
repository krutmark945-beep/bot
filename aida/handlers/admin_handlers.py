import asyncio
import json
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS
from database.db import Database
from services.ad_service import AdService
from keyboards.admin_kb import (
    get_admin_main_kb,
    get_series_admin_kb,
    get_ads_admin_kb,
    get_settings_kb,
    get_ad_toggle_kb,
    get_series_list_kb,
    get_series_view_kb,
    get_ads_list_kb,
)

logger = logging.getLogger(__name__)

router = Router()


class AdminSeriesStates(StatesGroup):
    waiting_title = State()
    waiting_number = State()
    waiting_video = State()
    fast_upload = State()


class AdminAdStates(StatesGroup):
    waiting_content = State()
    waiting_button_text = State()
    waiting_button_url = State()


class AdminSettingsStates(StatesGroup):
    waiting_interval_hours = State()
    waiting_interval_minutes = State()
    waiting_channel_id = State()
    waiting_storage_channel_id = State()


def register_admin_handlers(dp, db: Database, ad_service: AdService):
    dp.include_router(router)
    router.db = db  # type: ignore
    router.ad_service = ad_service  # type: ignore


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ---------------- вход в админ-панель ----------------

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await message.answer("🔐 Админ-панель:", reply_markup=get_admin_main_kb())


@router.message(F.text == "🔙 Выйти из админ-режима")
async def admin_exit(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Вы вышли из админ-режима.", reply_markup=get_admin_main_kb())


# ---------------- серии ----------------

@router.message(F.text == "⚡ Быстрая загрузка")
async def admin_fast_upload_start(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminSeriesStates.fast_upload)
    await message.answer(
        "⚡ <b>Режим быстрой загрузки включён.</b>\n\n"
        "Просто присылайте видео одно за другим.\n"
        "Каждое новое видео станет следующей серией:\n"
        "первое = 1 серия, второе = 2 серия и т.д.\n\n"
        "Название будет автоматическим («Серия N»).\n"
        "Чтобы выйти — нажмите «🔙 Назад».",
        reply_markup=get_series_admin_kb(),
    )


async def _save_next_series(message: Message, file_id: str, file_unique_id: str | None, storage_message_id: int | None = None) -> int:
    """Сохраняет видео как следующую серию и возвращает её номер."""
    db: Database = message.bot.db  # type: ignore
    series_list = await db.get_all_series()
    next_number = max((s["series_number"] for s in series_list), default=0) + 1
    title = f"Серия {next_number}"
    await db.add_series(
        title=title,
        series_number=next_number,
        file_id=file_id,
        file_unique_id=file_unique_id,
        storage_message_id=storage_message_id,
    )
    return next_number


@router.message(AdminSeriesStates.fast_upload, F.video & ~F.forward_from_chat)
async def admin_fast_upload_video(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    number = await _save_next_series(
        message,
        message.video.file_id,
        message.video.file_unique_id,
    )
    await message.answer(
        f"✅ Серия #{number} добавлена. Пришлите следующее видео.",
        reply_markup=get_series_admin_kb(),
    )


@router.message(AdminSeriesStates.fast_upload, F.forward_from_chat)
async def admin_fast_upload_forward(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    if not message.video:
        await message.answer("В пересланном сообщении нет видео. Пришлите видео напрямую.")
        return
    number = await _save_next_series(
        message,
        message.video.file_id,
        message.video.file_unique_id,
        message.forward_from_message_id,
    )
    await message.answer(
        f"✅ Серия #{number} добавлена из пересланного сообщения. Пришлите следующее видео.",
        reply_markup=get_series_admin_kb(),
    )


@router.message(F.text == "➕ Добавить серию")
async def admin_add_series_start(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminSeriesStates.waiting_title)
    await message.answer("Введите название серии:")


@router.message(AdminSeriesStates.waiting_title)
async def admin_add_series_title(message: Message, state: FSMContext):
    await state.update_data(title=message.text)
    await state.set_state(AdminSeriesStates.waiting_number)
    await message.answer("Введите номер серии (целое число):")


@router.message(AdminSeriesStates.waiting_number)
async def admin_add_series_number(message: Message, state: FSMContext):
    try:
        number = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно целое число. Попробуйте ещё раз:")
        return
    await state.update_data(series_number=number)
    await state.set_state(AdminSeriesStates.waiting_video)
    await message.answer(
        "Пришлите видео (файл) или перешлите сообщение из канала-хранилища, "
        "чтобы бот получил file_id."
    )


@router.message(Command("addseries"))
async def cmd_add_series(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminSeriesStates.waiting_title)
    await message.answer("Введите название серии:")


@router.message(AdminSeriesStates.waiting_video, F.video & ~F.forward_from_chat)
async def admin_add_series_video(message: Message, state: FSMContext):
    db: Database = message.bot.db  # type: ignore
    data = await state.get_data()
    file_id = message.video.file_id
    file_unique_id = message.video.file_unique_id

    await db.add_series(
        title=data["title"],
        series_number=data["series_number"],
        file_id=file_id,
        file_unique_id=file_unique_id,
    )
    await state.clear()
    await message.answer(
        f"✅ Серия #{data['series_number']} «{data['title']}» добавлена.",
        reply_markup=get_series_admin_kb(),
    )


@router.message(AdminSeriesStates.waiting_video, F.forward_from_chat)
async def admin_add_series_forward(message: Message, state: FSMContext):
    db: Database = message.bot.db  # type: ignore
    data = await state.get_data()
    # file_id из пересланного сообщения
    file_id = message.video.file_id if message.video else None
    if not file_id:
        await message.answer("В пересланном сообщении не найдено видео.")
        return

    await db.add_series(
        title=data["title"],
        series_number=data["series_number"],
        file_id=file_id,
        storage_message_id=message.forward_from_message_id,
    )
    await state.clear()
    await message.answer(
        f"✅ Серия #{data['series_number']} «{data['title']}» добавлена из пересланного сообщения.",
        reply_markup=get_series_admin_kb(),
    )


@router.message(AdminSeriesStates.waiting_video, F.video & F.caption)
async def admin_add_series_video_caption(message: Message, state: FSMContext):
    """
    Если видео прислано с подписью в формате 'Название | Номер',
    загружаем серию за один шаг без FSM.
    """
    db: Database = message.bot.db  # type: ignore
    caption = message.caption or ""
    if "|" not in caption:
        await message.answer(
            "Подпись не содержит разделителя '|'. "
            "Используйте формат: Название серии | Номер серии\n"
            "Например: Приключения | 1"
        )
        return

    parts = caption.split("|", 1)
    title = parts[0].strip()
    try:
        number = int(parts[1].strip())
    except ValueError:
        await message.answer("Номер серии после '|' должен быть целым числом.")
        return

    file_id = message.video.file_id
    file_unique_id = message.video.file_unique_id

    await db.add_series(
        title=title,
        series_number=number,
        file_id=file_id,
        file_unique_id=file_unique_id,
    )
    await state.clear()
    await message.answer(
        f"✅ Серия #{number} «{title}» добавлена за один шаг.",
        reply_markup=get_series_admin_kb(),
    )


@router.message(F.text == "📋 Список серий")
async def admin_series_list(message: Message):
    if not _is_admin(message.from_user.id):
        return
    db: Database = message.bot.db  # type: ignore
    series_list = await db.get_all_series()
    if not series_list:
        await message.answer("Серии не найдены.")
        return
    await message.answer(
        "Список серий:", reply_markup=get_series_list_kb(series_list, mode="view")
    )


@router.callback_query(F.data.startswith("series_view:"))
async def admin_series_view(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    db: Database = callback.bot.db  # type: ignore
    series_id = int(callback.data.split(":")[1])
    series = await db.get_series(series_id)
    if not series:
        await callback.answer("Серия не найдена", show_alert=True)
        return
    text = (
        f"ID: {series['id']}\n"
        f"Название: {series['title']}\n"
        f"Номер: {series['series_number']}\n"
        f"file_id: {series['file_id'][:30]}..."
    )
    await callback.message.edit_text(text, reply_markup=get_series_view_kb(series_id))
    await callback.answer()


@router.message(F.text == "🗑 Удалить серию")
async def admin_delete_series_prompt(message: Message):
    if not _is_admin(message.from_user.id):
        return
    db: Database = message.bot.db  # type: ignore
    series_list = await db.get_all_series()
    if not series_list:
        await message.answer("Серии не найдены.")
        return
    await message.answer(
        "Выберите серию для удаления:",
        reply_markup=get_series_list_kb(series_list, mode="delete"),
    )


@router.callback_query(F.data.startswith("series_delete:"))
async def admin_series_delete(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    db: Database = callback.bot.db  # type: ignore
    series_id = int(callback.data.split(":")[1])
    ok = await db.delete_series(series_id)
    await callback.answer("Удалено" if ok else "Не найдено", show_alert=True)
    series_list = await db.get_all_series()
    if series_list:
        await callback.message.edit_text(
            "Список серий:", reply_markup=get_series_list_kb(series_list, mode="delete")
        )
    else:
        await callback.message.edit_text("Серии не найдены.")


@router.callback_query(F.data == "admin_back")
async def admin_back_cb(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    if not _is_admin(callback.from_user.id):
        return
    try:
        await callback.message.delete()
    except Exception:
        pass
    await callback.message.answer("Админ-панель:", reply_markup=get_admin_main_kb())
    await callback.answer()


# ---------------- реклама ----------------

# Буфер для сбора альбомов (несколько фото/видео в одном сообщении)
_album_buffer: dict[str, dict] = {}
_album_tasks: dict[str, asyncio.Task] = {}


def _extract_media_item(message: Message) -> dict | None:
    if message.photo:
        return {"type": "photo", "file_id": message.photo[-1].file_id}
    if message.video:
        return {"type": "video", "file_id": message.video.file_id}
    return None


async def _finalize_album(key: str, bot, state: FSMContext) -> None:
    """Через небольшую паузу собирает все части альбома и сохраняет их в состояние."""
    await asyncio.sleep(1.2)
    buf = _album_buffer.pop(key, None)
    _album_tasks.pop(key, None)
    if not buf:
        return

    items = buf["items"]
    caption = buf["caption"]
    chat_id = buf["chat_id"]

    if len(items) == 1:
        await state.update_data(
            content_type=items[0]["type"],
            file_id=items[0]["file_id"],
            media=None,
            text=caption,
        )
    else:
        await state.update_data(
            content_type="album",
            file_id=None,
            media=json.dumps(items),
            text=caption,
        )

    await state.set_state(AdminAdStates.waiting_button_text)
    await bot.send_message(
        chat_id,
        f"📎 Получено медиа: {len(items)}. "
        f"Введите текст кнопки (или '-' если без кнопки):",
    )


@router.message(F.text == "📢 Реклама")
async def admin_ads(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("Управление рекламой:", reply_markup=get_ads_admin_kb())


@router.message(F.text == "➕ Добавить рекламу")
async def admin_add_ad_start(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminAdStates.waiting_content)
    await message.answer(
        "Пришлите рекламный контент: текст, одно фото/видео "
        "или альбом (несколько фото/видео сразу).\n\n"
        "Подпись к медиа станет текстом объявления."
    )


@router.message(AdminAdStates.waiting_content, F.photo | F.video)
async def admin_add_ad_media(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    item = _extract_media_item(message)
    if not item:
        return

    # Альбом: несколько сообщений с общим media_group_id
    if message.media_group_id:
        key = f"{message.from_user.id}:{message.media_group_id}"
        buf = _album_buffer.setdefault(
            key,
            {"items": [], "caption": None, "chat_id": message.chat.id},
        )
        buf["items"].append(item)
        if message.caption:
            buf["caption"] = message.caption

        # Перезапускаем таймер ожидания, пока не придут все части альбома
        old = _album_tasks.get(key)
        if old and not old.done():
            old.cancel()
        _album_tasks[key] = asyncio.create_task(
            _finalize_album(key, message.bot, state)
        )
        return

    # Одиночное фото/видео
    await state.update_data(
        content_type=item["type"],
        file_id=item["file_id"],
        media=None,
        text=message.caption,
    )
    await state.set_state(AdminAdStates.waiting_button_text)
    await message.answer("Введите текст кнопки (или '-' если без кнопки):")


@router.message(AdminAdStates.waiting_content, F.text)
async def admin_add_ad_text(message: Message, state: FSMContext):
    await state.update_data(
        content_type="text", file_id=None, media=None, text=message.text
    )
    await state.set_state(AdminAdStates.waiting_button_text)
    await message.answer("Введите текст кнопки (или '-' если без кнопки):")


@router.message(AdminAdStates.waiting_button_text)
async def admin_add_ad_button_text(message: Message, state: FSMContext):
    if not message.text:
        return
    btn_text = None if message.text.strip() == "-" else message.text.strip()
    await state.update_data(button_text=btn_text)
    await state.set_state(AdminAdStates.waiting_button_url)
    await message.answer("Введите ссылку кнопки (или '-' если без ссылки):")


@router.message(AdminAdStates.waiting_button_url)
async def admin_add_ad_button_url(message: Message, state: FSMContext):
    if not message.text:
        return
    db: Database = message.bot.db  # type: ignore
    data = await state.get_data()
    btn_url = None if message.text.strip() == "-" else message.text.strip()

    await db.add_ad(
        content_type=data["content_type"],
        text=data.get("text"),
        file_id=data.get("file_id"),
        button_text=data.get("button_text"),
        button_url=btn_url,
        is_active=True,
        media=data.get("media"),
    )
    await state.clear()
    await message.answer("✅ Рекламный пост добавлен.", reply_markup=get_ads_admin_kb())


@router.message(F.text == "📋 Список рекламы")
async def admin_ads_list(message: Message):
    if not _is_admin(message.from_user.id):
        return
    db: Database = message.bot.db  # type: ignore
    ads = await db.get_all_ads()
    if not ads:
        await message.answer("Реклама не найдена.")
        return
    await message.answer(
        "Список рекламных постов:", reply_markup=get_ads_list_kb(ads)
    )


@router.callback_query(F.data.startswith("ad_view:"))
async def admin_ad_view(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    db: Database = callback.bot.db  # type: ignore
    ad_id = int(callback.data.split(":")[1])
    ad = await db.get_ad(ad_id)
    if not ad:
        await callback.answer("Не найдено", show_alert=True)
        return
    status = "✅ Активно" if ad["is_active"] else "❌ Выключено"
    text = (
        f"ID: {ad['id']}\n"
        f"Тип: {ad['content_type']}\n"
        f"Текст: {ad['text'] or '-'}\n"
        f"Кнопка: {ad['button_text'] or '-'} ({ad['button_url'] or '-'})\n"
        f"Статус: {status}"
    )
    await callback.message.edit_text(text, reply_markup=get_ad_toggle_kb(ad_id, ad["is_active"]))
    await callback.answer()


@router.callback_query(F.data.startswith("ad_toggle:"))
async def admin_ad_toggle(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    db: Database = callback.bot.db  # type: ignore
    ad_id = int(callback.data.split(":")[1])
    ad = await db.get_ad(ad_id)
    if not ad:
        await callback.answer("Не найдено", show_alert=True)
        return
    await db.set_ad_active(ad_id, not ad["is_active"])
    await callback.answer("Статус изменён")
    await callback.message.edit_text(
        "Список рекламных постов:", reply_markup=get_ads_list_kb(await db.get_all_ads())
    )


@router.callback_query(F.data.startswith("ad_delete:"))
async def admin_ad_delete(callback: CallbackQuery):
    if not _is_admin(callback.from_user.id):
        return
    db: Database = callback.bot.db  # type: ignore
    ad_id = int(callback.data.split(":")[1])
    ok = await db.delete_ad(ad_id)
    await callback.answer("Удалено" if ok else "Не найдено", show_alert=True)
    ads = await db.get_all_ads()
    if ads:
        await callback.message.edit_text(
            "Список рекламных постов:", reply_markup=get_ads_list_kb(ads)
        )
    else:
        await callback.message.edit_text("Реклама не найдена.")


# ---------------- настройки ----------------

@router.message(F.text == "⚙️ Настройки")
async def admin_settings(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.clear()
    await message.answer("Настройки:", reply_markup=get_settings_kb())


@router.message(F.text == "📺 Канал подписки")
async def admin_set_channel(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminSettingsStates.waiting_channel_id)
    await message.answer("Введите числовой ID канала подписки (-100...):")


@router.message(AdminSettingsStates.waiting_channel_id)
async def admin_set_channel_save(message: Message, state: FSMContext):
    from config import REQUIRED_CHANNEL_ID

    try:
        cid = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно числовое ID. Попробуйте ещё:")
        return
    db: Database = message.bot.db  # type: ignore
    await db.set_setting("required_channel_id", str(cid))
    await state.clear()
    await message.answer(f"✅ Канал подписки установлен: {cid}", reply_markup=get_settings_kb())


@router.message(F.text == "💾 Канал хранилища")
async def admin_set_storage(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminSettingsStates.waiting_storage_channel_id)
    await message.answer("Введите числовой ID канала-хранилища (-100...):")


@router.message(AdminSettingsStates.waiting_storage_channel_id)
async def admin_set_storage_save(message: Message, state: FSMContext):
    try:
        cid = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно числовое ID. Попробуйте ещё:")
        return
    db: Database = message.bot.db  # type: ignore
    await db.set_setting("storage_channel_id", str(cid))
    await state.clear()
    await message.answer(f"✅ Канал хранилища установлен: {cid}", reply_markup=get_settings_kb())


@router.message(F.text == "⚙️ Интервал рекламы")
async def admin_ad_interval(message: Message, state: FSMContext):
    if not _is_admin(message.from_user.id):
        return
    await state.set_state(AdminSettingsStates.waiting_interval_hours)
    await message.answer(
        "Задайте интервал показа рекламы.\nВведите количество часов (или 0):"
    )


@router.message(AdminSettingsStates.waiting_interval_hours)
async def admin_ad_interval_hours(message: Message, state: FSMContext):
    try:
        hours = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно целое число. Попробуйте ещё:")
        return
    await state.update_data(interval_hours=hours)
    await state.set_state(AdminSettingsStates.waiting_interval_minutes)
    await message.answer("Введите количество минут (или 0):")


@router.message(AdminSettingsStates.waiting_interval_minutes)
async def admin_ad_interval_minutes(message: Message, state: FSMContext):
    try:
        minutes = int(message.text.strip())
    except ValueError:
        await message.answer("Нужно целое число. Попробуйте ещё:")
        return
    data = await state.get_data()
    db: Database = message.bot.db  # type: ignore
    await db.set_setting("ad_interval_hours", str(data["interval_hours"]))
    await db.set_setting("ad_interval_minutes", str(minutes))
    await state.clear()
    await message.answer(
        f"✅ Интервал установлен: {data['interval_hours']} ч {minutes} мин",
        reply_markup=get_ads_admin_kb(),
    )


@router.message(F.text == "🔁 Рассылка")
async def admin_broadcast_toggle(message: Message):
    if not _is_admin(message.from_user.id):
        return
    db: Database = message.bot.db  # type: ignore
    current = await db.get_setting("broadcast_enabled")
    new_value = "0" if current == "1" else "1"
    await db.set_setting("broadcast_enabled", new_value)
    state_text = "🟢 ВКЛЮЧЕНА" if new_value == "1" else "🔴 ВЫКЛЮЧЕНА"
    check_seconds = await db.get_setting("broadcast_check_seconds") or "60"
    hours = await db.get_setting("ad_interval_hours") or "0"
    minutes = await db.get_setting("ad_interval_minutes") or "0"
    await message.answer(
        f"Фоновая рассылка рекламы: {state_text}\n\n"
        f"• Интервал показа: {hours} ч {minutes} мин\n"
        f"• Проверка каждые: {check_seconds} сек\n\n"
        f"Нажмите «🔁 Рассылка», чтобы переключить.",
        reply_markup=get_ads_admin_kb(),
    )


@router.message(F.text == "📤 Разослать сейчас")
async def admin_broadcast_now(message: Message):
    if not _is_admin(message.from_user.id):
        return
    ad_service: AdService = message.bot.ad_service  # type: ignore
    await message.answer("⏳ Начинаю рассылку...")
    sent = await ad_service.broadcast_once()
    await message.answer(
        f"✅ Рассылка завершена. Отправлено сообщений: {sent}",
        reply_markup=get_ads_admin_kb(),
    )


# ---------------- пользователи ----------------

@router.message(F.text == "👥 Пользователи")
async def admin_users(message: Message):
    if not _is_admin(message.from_user.id):
        return
    db: Database = message.bot.db  # type: ignore
    users = await db.get_all_users()
    if not users:
        await message.answer("Пользователей нет.")
        return
    text = "👥 Пользователи:\n\n"
    for u in users[:20]:
        text += f"ID: {u['user_id']} | {u['first_name'] or ''} @{u['username'] or '-'}\n"
    await message.answer(text)


@router.message(F.text == "📊 Статистика")
async def admin_stats(message: Message):
    if not _is_admin(message.from_user.id):
        return
    db: Database = message.bot.db  # type: ignore

    day = await db.get_users_stats(1)
    month = await db.get_users_stats(30)

    def _format_users(users: list[dict]) -> str:
        if not users:
            return "—\n"
        lines = []
        for u in users[:20]:
            name = u["first_name"] or u["last_name"] or ""
            lines.append(f"ID: {u['user_id']} | {name} @{u['username'] or '-'}")
        return "\n".join(lines) + "\n"

    text = (
        "📊 <b>Статистика пользователей</b>\n\n"
        f"📅 За 1 день: <b>{day['count']}</b> чел.\n"
        f"{_format_users(day['users'])}"
        f"📅 За 30 дней: <b>{month['count']}</b> чел.\n"
        f"{_format_users(month['users'])}"
    )
    await message.answer(text)