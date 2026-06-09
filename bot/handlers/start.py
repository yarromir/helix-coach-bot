"""онбординг: обязательный пошаговый опрос + расчёт нормы и генерация программы."""
from __future__ import annotations

import logging
import re

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.db import Database
from bot.database.models import GOALS, LEVELS, SEXES
from bot.keyboards import (
    goal_kb,
    level_kb,
    main_menu_kb,
    sex_kb,
    workouts_kb,
)
from bot.services.ai import AIUnavailable, ai_service
from bot.states import Onboarding
from bot.utils.calc import calc_targets
from bot.utils.text_gen import fallback_program

logger = logging.getLogger(__name__)
router = Router()

TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*(.*)$")


def _num(text: str) -> float | None:
    m = re.search(r"-?\d+[.,]?\d*", text.replace(",", "."))
    return float(m.group()) if m else None


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db: Database) -> None:
    await state.clear()
    user = message.from_user
    await db.ensure_user(user.id, user.username if user else None)
    profile = await db.get_user(user.id)
    if profile and profile.get("onboarded"):
        await message.answer(
            "о, ты вернулся. главное меню снизу. жми /помощь если забыл команды.",
            reply_markup=main_menu_kb,
        )
        return
    await message.answer(
        "погнали онбординг, опытный. отвечай честно, без пиздежа.\n\n"
        "1. какая цель?",
        reply_markup=goal_kb,
    )
    await state.set_state(Onboarding.goal)


@router.callback_query(Onboarding.goal, F.data.startswith("goal:"))
async def on_goal(cb: CallbackQuery, state: FSMContext) -> None:
    goal = cb.data.split(":", 1)[1]
    await state.update_data(goal=goal)
    await cb.message.edit_text(f"цель: {GOALS[goal]}.\n\n2. пол?")
    await cb.message.answer("выбери:", reply_markup=sex_kb)
    await state.set_state(Onboarding.sex)
    await cb.answer()


@router.callback_query(Onboarding.sex, F.data.startswith("sex:"))
async def on_sex(cb: CallbackQuery, state: FSMContext) -> None:
    sex = cb.data.split(":", 1)[1]
    await state.update_data(sex=sex)
    await cb.message.edit_text(f"пол: {SEXES[sex]}.\n\n3. возраст? (число)")
    await state.set_state(Onboarding.age)
    await cb.answer()


@router.message(Onboarding.age)
async def on_age(message: Message, state: FSMContext) -> None:
    age = _num(message.text or "")
    if not age or not (10 <= age <= 100):
        await message.answer("введи нормальный возраст числом, не выёбывайся")
        return
    await state.update_data(age=int(age))
    await message.answer("4. рост в см?")
    await state.set_state(Onboarding.height)


@router.message(Onboarding.height)
async def on_height(message: Message, state: FSMContext) -> None:
    h = _num(message.text or "")
    if not h or not (120 <= h <= 230):
        await message.answer("рост в см, числом. например 182")
        return
    await state.update_data(height=h)
    await message.answer("5. вес в кг?")
    await state.set_state(Onboarding.weight)


@router.message(Onboarding.weight)
async def on_weight(message: Message, state: FSMContext) -> None:
    w = _num(message.text or "")
    if not w or not (30 <= w <= 300):
        await message.answer("вес в кг, числом. например 88")
        return
    await state.update_data(weight=w)
    await message.answer("6. уровень подготовки?", reply_markup=level_kb)
    await state.set_state(Onboarding.level)


@router.callback_query(Onboarding.level, F.data.startswith("level:"))
async def on_level(cb: CallbackQuery, state: FSMContext) -> None:
    level = cb.data.split(":", 1)[1]
    await state.update_data(level=level)
    await cb.message.edit_text(
        f"уровень: {LEVELS[level]}.\n\n"
        "7. доступное оборудование? напиши, что есть "
        "(зал: скамья, штанги, гантели, тренажёры; или дом/улица)"
    )
    await state.set_state(Onboarding.equipment)
    await cb.answer()


@router.message(Onboarding.equipment)
async def on_equipment(message: Message, state: FSMContext) -> None:
    await state.update_data(equipment=(message.text or "").strip())
    await message.answer("8. сколько тренировок в неделю?", reply_markup=workouts_kb)
    await state.set_state(Onboarding.workouts)


@router.callback_query(Onboarding.workouts, F.data.startswith("wpw:"))
async def on_workouts(cb: CallbackQuery, state: FSMContext) -> None:
    wpw = int(cb.data.split(":", 1)[1])
    await state.update_data(workouts_per_week=wpw)
    await cb.message.edit_text(
        f"тренировок в неделю: {wpw}.\n\n"
        "9. травмы / ограничения / противопоказания? "
        "(свободный текст, напр. «больная спина L4-L5» или «нет ограничений»)"
    )
    await state.set_state(Onboarding.injuries)
    await cb.answer()


@router.message(Onboarding.injuries)
async def on_injuries(message: Message, state: FSMContext) -> None:
    await state.update_data(injuries=(message.text or "").strip())
    await message.answer("10. текущая программа, если есть? (свободный текст или «нет»)")
    await state.set_state(Onboarding.program)


@router.message(Onboarding.program)
async def on_program(message: Message, state: FSMContext) -> None:
    await state.update_data(current_program=(message.text or "").strip())
    await message.answer(
        "11. в какое время присылать напоминание о тренировке? "
        "формат чч:мм, можно указать часовой пояс (по умолчанию мск). "
        "напр. «08:30» или «08:30 Asia/Yekaterinburg»"
    )
    await state.set_state(Onboarding.reminder)


@router.message(Onboarding.reminder)
async def on_reminder(message: Message, state: FSMContext) -> None:
    m = TIME_RE.match(message.text or "")
    if not m:
        await message.answer("формат чч:мм, например 08:30. давай ещё раз")
        return
    hh, mm = int(m.group(1)), int(m.group(2))
    if not (0 <= hh < 24 and 0 <= mm < 60):
        await message.answer("такого времени не бывает. чч:мм, например 08:30")
        return
    tz = m.group(3).strip() or "Europe/Moscow"
    await state.update_data(reminder_time=f"{hh:02d}:{mm:02d}", reminder_tz=tz)
    await message.answer(
        "12. есть продукты, которые не ешь или ненавидишь? (аллергии, нелюбимое; или «нет»)"
    )
    await state.set_state(Onboarding.food)


@router.message(Onboarding.food)
async def on_food(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    data["food_dislikes"] = (message.text or "").strip()

    targets = calc_targets(
        sex=data["sex"], weight=data["weight"], height=data["height"],
        age=data["age"], goal=data["goal"], workouts_per_week=data["workouts_per_week"],
    )
    await db.update_user(
        message.from_user.id,
        goal=data["goal"], sex=data["sex"], age=data["age"], height=data["height"],
        weight=data["weight"], level=data["level"], equipment=data["equipment"],
        workouts_per_week=data["workouts_per_week"], injuries=data["injuries"],
        current_program=data["current_program"], reminder_time=data["reminder_time"],
        reminder_tz=data["reminder_tz"], food_dislikes=data["food_dislikes"],
        calories_target=targets.calories, protein_target=targets.protein,
        fat_target=targets.fat, carb_target=targets.carb, onboarded=1,
    )
    await state.clear()

    await message.answer(
        "онбординг закрыт. посчитал твою норму:\n"
        f"калории: {targets.calories:g} ккал\n"
        f"белок: {targets.protein:g} г | жиры: {targets.fat:g} г | углеводы: {targets.carb:g} г\n"
        f"(базовый обмен {targets.bmr:g}, расход {targets.tdee:g})\n\n"
        "пишу программу, подожди...",
        reply_markup=main_menu_kb,
    )

    profile = await db.get_user(message.from_user.id)
    try:
        program = await ai_service.generate_program(profile)
    except AIUnavailable:
        program = fallback_program(
            profile["goal"], profile["workouts_per_week"], profile["injuries"]
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("ошибка генерации программы")
        program = fallback_program(
            profile["goal"], profile["workouts_per_week"], profile["injuries"]
        )
        program += f"\n\n(ии отвалился: {e})"

    await db.save_program(message.from_user.id, program, profile.get("cycle_weeks", 4))
    await message.answer(program)
