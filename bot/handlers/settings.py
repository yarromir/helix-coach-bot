"""настройки: время напоминаний, кол-во тренировок, цель, оборудование, тумблеры."""
from __future__ import annotations

import re

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot.database.db import Database
from bot.database.models import GOALS
from bot.handlers.reminders import schedule_user
from bot.keyboards import goal_kb, settings_kb, workouts_kb
from bot.states import SettingsFlow
from bot.utils.calc import calc_targets

router = Router()

TIME_RE = re.compile(r"^\s*(\d{1,2})[:.](\d{2})\s*(.*)$")


async def _recalc_targets(db: Database, uid: int) -> None:
    p = await db.get_user(uid)
    if not p or not all(p.get(k) is not None for k in ("sex", "weight", "height", "age", "goal")):
        return
    t = calc_targets(p["sex"], p["weight"], p["height"], p["age"], p["goal"],
                     p["workouts_per_week"] or 3)
    await db.update_user(
        uid, calories_target=t.calories, protein_target=t.protein,
        fat_target=t.fat, carb_target=t.carb,
    )


@router.message(Command("настройки"))
async def cmd_settings(message: Message, state: FSMContext, db: Database) -> None:
    profile = await db.get_user(message.from_user.id)
    if not profile or not profile.get("onboarded"):
        await message.answer("сначала онбординг — /start")
        return
    rem = "вкл" if profile.get("reminders_enabled") else "выкл"
    chk = "вкл" if profile.get("checkin_enabled") else "выкл"
    await message.answer(
        f"настройки. сейчас:\n"
        f"напоминания: {rem} ({profile.get('reminder_time')} {profile.get('reminder_tz')})\n"
        f"чек-ин: {chk}\n"
        f"тренировок/неделю: {profile.get('workouts_per_week')}\n"
        f"цель: {GOALS.get(profile.get('goal'), '?')}\n"
        f"что меняем?",
        reply_markup=settings_kb(),
    )
    await state.set_state(SettingsFlow.choosing)


@router.callback_query(SettingsFlow.choosing, F.data == "set:reminder")
async def set_reminder(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(field="reminder")
    await cb.message.edit_text("новое время напоминания, чч:мм [часовой пояс]. напр. «07:45»")
    await state.set_state(SettingsFlow.value)
    await cb.answer()


@router.callback_query(SettingsFlow.choosing, F.data == "set:workouts")
async def set_workouts(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(field="workouts")
    await cb.message.edit_text("сколько тренировок в неделю?")
    await cb.message.answer("выбери:", reply_markup=workouts_kb)
    await state.set_state(SettingsFlow.value)
    await cb.answer()


@router.callback_query(SettingsFlow.choosing, F.data == "set:goal")
async def set_goal(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(field="goal")
    await cb.message.edit_text("новая цель?")
    await cb.message.answer("выбери:", reply_markup=goal_kb)
    await state.set_state(SettingsFlow.value)
    await cb.answer()


@router.callback_query(SettingsFlow.choosing, F.data == "set:equipment")
async def set_equipment(cb: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(field="equipment")
    await cb.message.edit_text("опиши доступное оборудование заново")
    await state.set_state(SettingsFlow.value)
    await cb.answer()


@router.callback_query(SettingsFlow.choosing, F.data == "set:toggle_rem")
async def toggle_rem(
    cb: CallbackQuery, state: FSMContext, db: Database, bot: Bot, scheduler: AsyncIOScheduler
) -> None:
    p = await db.get_user(cb.from_user.id)
    new = 0 if p.get("reminders_enabled") else 1
    await db.update_user(cb.from_user.id, reminders_enabled=new)
    schedule_user(scheduler, bot, db, await db.get_user(cb.from_user.id))
    await state.clear()
    await cb.message.edit_text(f"напоминания теперь {'вкл' if new else 'выкл'}.")
    await cb.answer()


@router.callback_query(SettingsFlow.choosing, F.data == "set:toggle_checkin")
async def toggle_checkin(
    cb: CallbackQuery, state: FSMContext, db: Database, bot: Bot, scheduler: AsyncIOScheduler
) -> None:
    p = await db.get_user(cb.from_user.id)
    new = 0 if p.get("checkin_enabled") else 1
    await db.update_user(cb.from_user.id, checkin_enabled=new)
    schedule_user(scheduler, bot, db, await db.get_user(cb.from_user.id))
    await state.clear()
    await cb.message.edit_text(f"чек-ин теперь {'вкл' if new else 'выкл'}.")
    await cb.answer()


@router.callback_query(SettingsFlow.value, F.data.startswith("wpw:"))
async def value_workouts(cb: CallbackQuery, state: FSMContext, db: Database) -> None:
    wpw = int(cb.data.split(":", 1)[1])
    await db.update_user(cb.from_user.id, workouts_per_week=wpw)
    await _recalc_targets(db, cb.from_user.id)
    await state.clear()
    await cb.message.edit_text(
        f"теперь {wpw} тренировок/неделю. норму пересчитал. "
        "сделай /коррекция чтобы перестроить сплит."
    )
    await cb.answer()


@router.callback_query(SettingsFlow.value, F.data.startswith("goal:"))
async def value_goal(cb: CallbackQuery, state: FSMContext, db: Database) -> None:
    goal = cb.data.split(":", 1)[1]
    await db.update_user(cb.from_user.id, goal=goal)
    await _recalc_targets(db, cb.from_user.id)
    await state.clear()
    await cb.message.edit_text(
        f"цель теперь: {GOALS[goal]}. норму пересчитал. "
        "сделай /коррекция чтобы перестроить программу."
    )
    await cb.answer()


@router.message(SettingsFlow.value)
async def value_text(
    message: Message, state: FSMContext, db: Database, bot: Bot, scheduler: AsyncIOScheduler
) -> None:
    data = await state.get_data()
    field = data.get("field")
    if field == "reminder":
        m = TIME_RE.match(message.text or "")
        if not m:
            await message.answer("формат чч:мм. ещё раз")
            return
        hh, mm = int(m.group(1)), int(m.group(2))
        if not (0 <= hh < 24 and 0 <= mm < 60):
            await message.answer("такого времени не бывает")
            return
        tz = m.group(3).strip() or (await db.get_user(message.from_user.id)).get("reminder_tz")
        await db.update_user(
            message.from_user.id, reminder_time=f"{hh:02d}:{mm:02d}", reminder_tz=tz
        )
        schedule_user(scheduler, bot, db, await db.get_user(message.from_user.id))
        await state.clear()
        await message.answer(f"буду напоминать в {hh:02d}:{mm:02d} ({tz}).")
    elif field == "equipment":
        await db.update_user(message.from_user.id, equipment=(message.text or "").strip())
        await state.clear()
        await message.answer("оборудование обновил. /коррекция перестроит под него.")
    else:
        await state.clear()
        await message.answer("непонятная настройка, начни заново /настройки")
