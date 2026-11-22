from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


def get_admin_main_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Серии"), KeyboardButton(text="📢 Реклама")],
            [KeyboardButton(text="⚙️ Настройки"), KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="🔙 Выйти из админ-режима")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Админ-панель",
    )
    return kb


def get_series_admin_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="⚡ Быстрая загрузка"), KeyboardButton(text="➕ Добавить серию")],
            [KeyboardButton(text="📋 Список серий"), KeyboardButton(text="🗑 Удалить серию")],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True,
    )
    return kb


def get_ads_admin_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➕ Добавить рекламу"), KeyboardButton(text="📋 Список рекламы")],
            [KeyboardButton(text="⚙️ Интервал рекламы"), KeyboardButton(text="🔁 Рассылка")],
            [KeyboardButton(text="📤 Разослать сейчас"), KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True,
    )
    return kb


def get_settings_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📺 Канал подписки"), KeyboardButton(text="💾 Канал хранилища")],
            [KeyboardButton(text="🔙 Назад")],
        ],
        resize_keyboard=True,
    )
    return kb


def get_ad_toggle_kb(ad_id: int, is_active: bool) -> InlineKeyboardMarkup:
    status_text = "🔴 Выключить" if is_active else "🟢 Включить"
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text=status_text, callback_data=f"ad_toggle:{ad_id}"),
                InlineKeyboardButton(text="🗑 Удалить", callback_data=f"ad_delete:{ad_id}"),
            ]
        ]
    )
    return kb


def get_series_list_kb(series_list: list[dict], mode: str = "view") -> InlineKeyboardMarkup:
    buttons = []
    for s in series_list:
        if mode == "delete":
            cb = f"series_delete:{s['id']}"
        else:
            cb = f"series_view:{s['id']}"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"#{s['series_number']} {s['title']}",
                    callback_data=cb,
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_series_view_kb(series_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗑 Удалить", callback_data=f"series_delete:{series_id}"
                ),
                InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back"),
            ]
        ]
    )
    return kb


def get_ads_list_kb(ads_list: list[dict]) -> InlineKeyboardMarkup:
    buttons = []
    for a in ads_list:
        mark = "✅" if a["is_active"] else "❌"
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"{mark} [{a['id']}] {a['text'] or a['content_type']} ({(a['text'] or '')[:30]})",
                    callback_data=f"ad_view:{a['id']}",
                )
            ]
        )
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)