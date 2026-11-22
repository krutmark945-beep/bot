from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🎬 Серии")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )
    return kb


def get_back_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад")]],
        resize_keyboard=True,
    )
    return kb