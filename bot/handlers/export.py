"""экспорт всех данных пользователя в csv (zip-архив из нескольких таблиц)."""
from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, Message

from bot.database.db import Database

router = Router()


def _csv_bytes(rows: list[dict], columns: list[str]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8-sig")


@router.message(Command("экспорт"))
async def cmd_export(message: Message, db: Database) -> None:
    uid = message.from_user.id
    profile = await db.get_user(uid)
    if not profile or not profile.get("onboarded"):
        await message.answer("сначала онбординг — /start")
        return

    workouts = await db.workout_logs(uid)
    metrics = await db.body_metrics(uid)
    nutrition = await db.nutrition_logs(uid)
    analyses = await db.analyses(uid)

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("profile.csv", _csv_bytes([profile], list(profile.keys())))
        zf.writestr("workouts.csv", _csv_bytes(
            workouts, ["log_date", "exercise", "weight", "reps", "sets", "volume"]))
        zf.writestr("body_metrics.csv", _csv_bytes(
            metrics, ["log_date", "weight", "chest", "waist", "hips", "biceps",
                      "wellbeing", "comment"]))
        zf.writestr("nutrition.csv", _csv_bytes(
            nutrition, ["log_date", "description", "kcal", "protein", "fat", "carb", "is_cheat"]))
        zf.writestr("analyses.csv", _csv_bytes(
            analyses, ["log_date", "indicator", "value", "units", "reference", "interpretation"]))
    zbuf.seek(0)

    fname = f"helix_export_{dt.date.today().isoformat()}.zip"
    await message.answer_document(
        BufferedInputFile(zbuf.read(), fname),
        caption="вот все твои данные: тренировки, замеры, питание, анализы, профиль.",
    )
