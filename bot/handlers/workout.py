"""модуль «тренер»: программа, запись тренировок, техника, прогресс, коррекция."""
from __future__ import annotations

import datetime as dt
import logging
import re

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, Message

from bot.database.db import Database
from bot.services import plot
from bot.services.ai import AIUnavailable, ai_service
from bot.states import CorrectionFlow, MetricFlow, TechniqueFlow, WorkoutFlow
from bot.utils.calc import epley_1rm, volume
from bot.utils.text_gen import fallback_program, progress_comment

logger = logging.getLogger(__name__)
router = Router()


async def _require(message: Message, db: Database) -> dict | None:
    profile = await db.get_user(message.from_user.id)
    if not profile or not profile.get("onboarded"):
        await message.answer("сначала пройди онбординг — жми /start")
        return None
    return profile


def _num(text: str) -> float | None:
    m = re.search(r"-?\d+[.,]?\d*", (text or "").replace(",", "."))
    return float(m.group()) if m else None


# ---------------- программа ----------------
@router.message(Command("программа"))
async def cmd_program(message: Message, db: Database) -> None:
    if not await _require(message, db):
        return
    prog = await db.latest_program(message.from_user.id)
    if not prog:
        await message.answer("программы пока нет. сделай /коррекция или пройди /start заново.")
        return
    await message.answer(prog["content"])


# ---------------- запись тренировки ----------------
@router.message(Command("тренировка"))
async def cmd_workout(message: Message, state: FSMContext, db: Database) -> None:
    if not await _require(message, db):
        return
    await message.answer("какое упражнение? (название). для выхода — /стоп")
    await state.set_state(WorkoutFlow.exercise)


@router.message(WorkoutFlow.exercise)
async def wf_exercise(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip().lower()
    if not name:
        await message.answer("название давай")
        return
    await state.update_data(exercise=name)
    await message.answer("вес снаряда, кг?")
    await state.set_state(WorkoutFlow.weight)


@router.message(WorkoutFlow.weight)
async def wf_weight(message: Message, state: FSMContext) -> None:
    w = _num(message.text or "")
    if w is None or w < 0:
        await message.answer("вес числом, кг")
        return
    await state.update_data(weight=w)
    await message.answer("сколько повторений?")
    await state.set_state(WorkoutFlow.reps)


@router.message(WorkoutFlow.reps)
async def wf_reps(message: Message, state: FSMContext) -> None:
    r = _num(message.text or "")
    if not r or r <= 0:
        await message.answer("повторения числом")
        return
    await state.update_data(reps=int(r))
    await message.answer("сколько подходов?")
    await state.set_state(WorkoutFlow.sets)


@router.message(WorkoutFlow.sets)
async def wf_sets(message: Message, state: FSMContext, db: Database) -> None:
    s = _num(message.text or "")
    if not s or s <= 0:
        await message.answer("подходы числом")
        return
    data = await state.get_data()
    exercise, weight, reps, sets = data["exercise"], data["weight"], data["reps"], int(s)

    prev = await db.exercise_history(message.from_user.id, exercise)
    await db.add_workout_log(message.from_user.id, exercise, weight, reps, sets)
    vol = volume(weight, reps, sets)
    one_rm = epley_1rm(weight, reps)

    comment = ""
    if prev:
        delta = vol - prev[-1]["volume"]
        comment = f"\n{progress_comment(delta)} (объём {vol:g}, было {prev[-1]['volume']:g})"
    else:
        comment = f"\nзаписал, объём {vol:g}"

    await message.answer(
        f"{exercise}: {weight:g}кг x {reps} x {sets}. 1ПМ ~{one_rm:.0f} кг.{comment}\n\n"
        "ещё упражнение? пиши название или /стоп чтобы закончить."
    )
    await state.set_state(WorkoutFlow.exercise)


# ---------------- техника ----------------
@router.message(Command("техника"))
async def cmd_technique(message: Message, state: FSMContext, db: Database) -> None:
    if not await _require(message, db):
        return
    await message.answer("описывай: что болит, где и на каком движении? (напр. «на жиме болит левое плечо»)")
    await state.set_state(TechniqueFlow.description)


@router.message(TechniqueFlow.description)
async def tf_desc(message: Message, state: FSMContext) -> None:
    desc = (message.text or "").strip()
    await state.clear()
    if len(desc) < 5:
        await message.answer("четко, блядь, что болит, где и на каком движении?")
        await state.set_state(TechniqueFlow.description)
        return
    try:
        answer = await ai_service.fix_technique(desc)
    except AIUnavailable:
        answer = (
            "ии выключен, но универсально: лопатки сведи, кор держи в напряжении, "
            "не гонись за весом и не дёргай рывком. если болит сустав — снизь вес и "
            "поставь технику. конкретику даст ии — подключи ключ."
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("ошибка техники")
        answer = f"ии отвалился ({e}). снизь вес, поставь технику, не геройствуй."
    await message.answer(answer)


# ---------------- замеры / самочувствие ----------------
@router.message(Command("замеры", "самочувствие"))
async def cmd_metrics(message: Message, state: FSMContext, db: Database) -> None:
    if not await _require(message, db):
        return
    await message.answer(
        "пиши через запятую, что есть:\n"
        "вес 88, грудь 110, талия 82, бёдра 100, бицепс 41, самочувствие 4, выспался норм"
    )
    await state.set_state(MetricFlow.value)


_FIELD_ALIASES = {
    "вес": "weight", "грудь": "chest", "талия": "waist", "бёдра": "hips",
    "бедра": "hips", "бицепс": "biceps", "самочувствие": "wellbeing",
}


@router.message(MetricFlow.value)
async def mf_value(message: Message, state: FSMContext, db: Database) -> None:
    text = (message.text or "").strip()
    fields: dict[str, float] = {}
    comment_parts: list[str] = []
    for chunk in re.split(r"[,;\n]", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        matched = False
        for ru, col in _FIELD_ALIASES.items():
            if chunk.lower().startswith(ru):
                val = _num(chunk)
                if val is not None:
                    fields[col] = int(val) if col == "wellbeing" else val
                    matched = True
                break
        if not matched:
            comment_parts.append(chunk)
    if "wellbeing" in fields:
        fields["wellbeing"] = max(1, min(5, int(fields["wellbeing"])))
    if comment_parts:
        fields["comment"] = ", ".join(comment_parts)
    if not fields:
        await message.answer("ничего не распознал. формат: «вес 88, талия 82, самочувствие 4»")
        return
    await db.add_body_metric(message.from_user.id, **fields)
    await state.clear()
    await message.answer("записал замеры. /прогресс покажет динамику.")


# ---------------- прогресс (графики) ----------------
@router.message(Command("прогресс"))
async def cmd_progress(message: Message, db: Database) -> None:
    profile = await _require(message, db)
    if not profile:
        return
    uid = message.from_user.id
    sent_any = False

    metrics = await db.body_metrics(uid)
    weights = [(m["log_date"], m["weight"]) for m in metrics if m["weight"] is not None]
    if weights:
        x = [dt.date.fromisoformat(d) for d, _ in weights]
        y = [v for _, v in weights]
        buf = plot.line_chart(x, y, "вес тела", "кг")
        await message.answer_photo(BufferedInputFile(buf.read(), "weight.png"), caption="вес тела")
        sent_any = True

    logs = await db.workout_logs(uid)
    if logs:
        by_date: dict[str, float] = {}
        for log in logs:
            by_date[log["log_date"]] = by_date.get(log["log_date"], 0.0) + log["volume"]
        dates = sorted(by_date)
        buf = plot.line_chart(
            [dt.date.fromisoformat(d) for d in dates], [by_date[d] for d in dates],
            "объём тренировок", "кг·повт",
        )
        await message.answer_photo(BufferedInputFile(buf.read(), "volume.png"), caption="объём по дням")
        sent_any = True

        # сила: 1ПМ по самому частому упражнению
        freq: dict[str, int] = {}
        for log in logs:
            freq[log["exercise"]] = freq.get(log["exercise"], 0) + 1
        top = max(freq, key=freq.get)
        hist = await db.exercise_history(uid, top)
        if len(hist) >= 2:
            buf = plot.line_chart(
                [dt.date.fromisoformat(h["log_date"]) for h in hist],
                [epley_1rm(h["weight"], h["reps"]) for h in hist],
                f"1ПМ: {top}", "кг",
            )
            await message.answer_photo(
                BufferedInputFile(buf.read(), "strength.png"), caption=f"сила: {top}"
            )

    totals = await db.nutrition_daily_totals(uid)
    if totals:
        buf = plot.line_chart(
            [dt.date.fromisoformat(t["log_date"]) for t in totals],
            [t["kcal"] for t in totals], "калории по дням", "ккал",
            target=profile.get("calories_target"),
        )
        await message.answer_photo(BufferedInputFile(buf.read(), "kcal.png"), caption="калории vs норма")
        sent_any = True

    if not sent_any:
        await message.answer("данных пока нет. позаписывай тренировки, вес и питание — будут графики.")


# ---------------- коррекция программы ----------------
@router.message(Command("коррекция"))
async def cmd_correction(message: Message, state: FSMContext, db: Database) -> None:
    if not await _require(message, db):
        return
    await message.answer("сколько дней пропустил? (число, 0 если не пропускал)")
    await state.set_state(CorrectionFlow.missed)


@router.message(CorrectionFlow.missed)
async def cf_missed(message: Message, state: FSMContext) -> None:
    n = _num(message.text or "")
    await state.update_data(missed=int(n) if n is not None else 0)
    await message.answer("как самочувствие? (свободный текст)")
    await state.set_state(CorrectionFlow.wellbeing)


@router.message(CorrectionFlow.wellbeing)
async def cf_well(message: Message, state: FSMContext) -> None:
    await state.update_data(wellbeing=(message.text or "").strip())
    await message.answer("жалобы/боль? (напр. «болят колени», или «нет»)")
    await state.set_state(CorrectionFlow.complaints)


@router.message(CorrectionFlow.complaints)
async def cf_complaints(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    complaints = (message.text or "").strip()
    await state.clear()
    profile = await db.get_user(message.from_user.id)
    await message.answer("перестраиваю, подожди...")
    try:
        result = await ai_service.adjust_program(
            profile, data.get("missed", 0), data.get("wellbeing", ""), complaints
        )
    except AIUnavailable:
        note = ""
        if data.get("missed", 0) > 3:
            note = "\nпропуск >3 дней — снизил объём первой тренировки на 30%, начни с разогрева."
        if "колен" in complaints.lower():
            note += "\nколени — приседания меняем на жим ногами/хак-присед."
        if "спин" in complaints.lower():
            note += "\nспина — становую и наклоны убираем, тяги делаем на блоке."
        result = fallback_program(
            profile["goal"], profile["workouts_per_week"], complaints or profile["injuries"]
        ) + note
    except Exception as e:  # noqa: BLE001
        logger.exception("ошибка коррекции")
        result = f"ии отвалился ({e}). снизь объём на 20–30%, щади больные суставы."
    await db.save_program(message.from_user.id, result, profile.get("cycle_weeks", 4))
    await message.answer(result)
