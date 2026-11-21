from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def get_subscription_kb(channel_url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📢 Перейти в канал", url=channel_url)],
            [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_subscription")],
        ]
    )
    return kb


def get_series_selection_kb(series_list: list[dict], page: int = 0, per_page: int = 8) -> InlineKeyboardMarkup:
    start = page * per_page
    end = start + per_page
    page_series = series_list[start:end]

    buttons = []
    for s in page_series:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"#{s['series_number']} {s['title']}",
                    callback_data=f"watch:{s['id']}",
                )
            ]
        )

    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ Назад", callback_data=f"series_page:{page - 1}"))
    if end < len(series_list):
        nav.append(InlineKeyboardButton(text="Вперёд ➡️", callback_data=f"series_page:{page + 1}"))
    if nav:
        buttons.append(nav)

    buttons.append([InlineKeyboardButton(text="🔙 Главное меню", callback_data="main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)