"""клавиатуры (reply / inline)."""
from __future__ import annotations

from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

remove = ReplyKeyboardRemove()


def _inline(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t, callback_data=cb) for t, cb in row] for row in rows
        ]
    )


goal_kb = _inline([
    [("набор массы", "goal:mass")],
    [("похудение", "goal:cut")],
    [("поддержка формы", "goal:maintain")],
])

sex_kb = _inline([[("мужской", "sex:male"), ("женский", "sex:female")]])

level_kb = _inline([
    [("новичок (<1 года)", "level:novice")],
    [("средний (1–3 года)", "level:medium")],
    [("продвинутый (3–5 лет)", "level:advanced")],
    [("эксперт (>5 лет)", "level:expert")],
])

workouts_kb = _inline([[(str(n), f"wpw:{n}") for n in (2, 3, 4)],
                       [(str(n), f"wpw:{n}") for n in (5, 6)]])

cheat_kb = _inline([[("обычный приём", "cheat:0"), ("это cheat-meal", "cheat:1")]])

analysis_confirm_kb = _inline([[("всё верно", "an:ok"), ("введу заново", "an:redo")]])

main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="/программа"), KeyboardButton(text="/тренировка")],
        [KeyboardButton(text="/питание"), KeyboardButton(text="/прогресс")],
        [KeyboardButton(text="/анализы"), KeyboardButton(text="/коррекция")],
        [KeyboardButton(text="/настройки"), KeyboardButton(text="/экспорт")],
        [KeyboardButton(text="/помощь")],
    ],
    resize_keyboard=True,
)


def settings_kb() -> InlineKeyboardMarkup:
    return _inline([
        [("время напоминаний", "set:reminder")],
        [("кол-во тренировок", "set:workouts")],
        [("цель", "set:goal")],
        [("оборудование", "set:equipment")],
        [("вкл/выкл напоминания", "set:toggle_rem")],
        [("вкл/выкл чек-ин", "set:toggle_checkin")],
    ])
