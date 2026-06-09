"""модуль «анализы helix»: загрузка (ocr/ручной ввод), расшифровка, динамика."""
from __future__ import annotations

import datetime as dt
import logging
from dataclasses import asdict

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.config import config
from bot.database.db import Database
from bot.keyboards import analysis_confirm_kb
from bot.services import plot
from bot.services.ai import AIUnavailable, ai_service
from bot.services.ocr import OCRUnavailable, extract_text
from bot.states import AnalysisFlow
from bot.utils.parser import AnalysisItem, parse_analysis_text
from bot.utils.text_gen import interpret_analysis, is_critical, normalize_indicator

logger = logging.getLogger(__name__)
router = Router()


async def _require(message: Message, db: Database) -> dict | None:
    profile = await db.get_user(message.from_user.id)
    if not profile or not profile.get("onboarded"):
        await message.answer("сначала онбординг — /start")
        return None
    return profile


@router.message(Command("анализы"))
async def cmd_analyses(message: Message, state: FSMContext, db: Database) -> None:
    if not await _require(message, db):
        return
    await message.answer(
        "пришли фото/скрин/pdf анализа из helix или лаборатории — распознаю.\n"
        "или введи вручную, одна строка — один показатель:\n"
        "«ферритин 8 нг/мл 20-250»\n\n"
        "история и графики — /история"
    )
    await state.set_state(AnalysisFlow.waiting_input)


@router.message(AnalysisFlow.waiting_input, F.photo | F.document)
async def af_file(message: Message, state: FSMContext) -> None:
    if message.photo:
        file_id = message.photo[-1].file_id
        suffix = ".jpg"
    else:
        file_id = message.document.file_id
        suffix = "." + (message.document.file_name or "file.bin").rsplit(".", 1)[-1].lower()
    path = config.db_path + f".upload_{message.from_user.id}{suffix}"
    await message.answer("распознаю, подожди...")
    try:
        await message.bot.download(file_id, destination=path)
        result = extract_text(path)
    except OCRUnavailable as e:
        await message.answer(
            f"ocr недоступен ({e}). введи значения вручную текстом, "
            "одна строка — один показатель."
        )
        return
    except Exception as e:  # noqa: BLE001
        logger.exception("ошибка ocr")
        await message.answer(f"не смог распознать ({e}). введи вручную текстом.")
        return

    items = parse_analysis_text(result.text)
    if not items:
        await message.answer(
            "ничего внятного не распознал. введи значения вручную текстом."
        )
        return
    warn = "\n⚠️ распознавание неуверенное, проверь внимательно!" if result.low_confidence else ""
    await _show_confirm(message, state, items, warn)


@router.message(AnalysisFlow.waiting_input)
async def af_text(message: Message, state: FSMContext) -> None:
    items = parse_analysis_text(message.text or "")
    if not items:
        await message.answer("не разобрал. формат: «ферритин 8 нг/мл 20-250»")
        return
    await _show_confirm(message, state, items, "")


async def _show_confirm(
    message: Message, state: FSMContext, items: list[AnalysisItem], warn: str
) -> None:
    await state.update_data(items=[asdict(i) for i in items])
    lines = [
        f"• {i.indicator}: {i.value if i.value is not None else '?'} "
        f"{i.units or ''} {('реф ' + i.reference) if i.reference else ''}".strip()
        for i in items
    ]
    await message.answer(
        "распознал такие показатели — всё верно?" + warn + "\n\n" + "\n".join(lines),
        reply_markup=analysis_confirm_kb,
    )
    await state.set_state(AnalysisFlow.confirm)


@router.callback_query(AnalysisFlow.confirm, F.data == "an:redo")
async def af_redo(cb: CallbackQuery, state: FSMContext) -> None:
    await cb.message.edit_text("ок, пришли заново — фото или текстом.")
    await state.set_state(AnalysisFlow.waiting_input)
    await cb.answer()


@router.callback_query(AnalysisFlow.confirm, F.data == "an:ok")
async def af_save(cb: CallbackQuery, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    items = [AnalysisItem(**d) for d in data.get("items", [])]
    await state.clear()
    uid = cb.from_user.id

    red_flags: list[str] = []
    fallback_lines: list[str] = []
    for item in items:
        prev = await db.previous_analysis(uid, normalize_indicator(item.indicator))
        text = interpret_analysis(item, prev)
        fallback_lines.append(text)
        if is_critical(item):
            red_flags.append(item.indicator)
        await db.add_analysis(
            uid, normalize_indicator(item.indicator), item.value, item.units,
            item.reference, text,
        )

    await cb.message.edit_text("сохранил. разбираю...")

    # таблица для ии
    table = "\n".join(
        f"{i.indicator}\t{i.value}\t{i.units or ''}\t{i.reference or ''}" for i in items
    )
    try:
        verdict = await ai_service.interpret_analyses(table)
    except AIUnavailable:
        verdict = "\n".join(fallback_lines)
    except Exception as e:  # noqa: BLE001
        logger.exception("ошибка расшифровки")
        verdict = "\n".join(fallback_lines) + f"\n\n(ии отвалился: {e})"

    if red_flags:
        verdict = (
            "🚩 ВНИМАНИЕ: критические отклонения — " + ", ".join(red_flags) +
            ". тяжёлые тренировки отмени, иди к врачу.\n\n" + verdict
        )
    await cb.message.answer(verdict)
    await cb.answer()


@router.message(Command("история"))
async def cmd_history(message: Message, db: Database) -> None:
    if not await _require(message, db):
        return
    rows = await db.analyses(message.from_user.id)
    if not rows:
        await message.answer("анализов в базе нет. загрузи через /анализы.")
        return

    by_ind: dict[str, list[dict]] = {}
    for r in rows:
        by_ind.setdefault(r["indicator"], []).append(r)

    summary = "\n".join(
        f"• {ind}: " + ", ".join(
            f"{x['log_date']}={x['value']:g}" for x in pts if x["value"] is not None
        )
        for ind, pts in by_ind.items()
    )
    await message.answer("история анализов:\n" + summary)

    for ind, pts in by_ind.items():
        valid = [(p["log_date"], p["value"]) for p in pts if p["value"] is not None]
        if len(valid) >= 2:
            buf = plot.line_chart(
                [dt.date.fromisoformat(d) for d, _ in valid],
                [v for _, v in valid], f"динамика: {ind}", ind,
            )
            await message.answer_photo(
                BufferedInputFile(buf.read(), f"{ind}.png"), caption=f"динамика: {ind}"
            )
