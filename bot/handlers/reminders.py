"""напоминания и мотивация через apscheduler.

- утреннее напоминание в указанное время
- pre-workout за ~45 мин до него
- опциональный ежедневный чек-ин
"""
from __future__ import annotations

import datetime as dt
import logging
import re

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bot.database.db import Database
from bot.utils.text_gen import morning_text

logger = logging.getLogger(__name__)

_SPLIT_RE = re.compile(r"тренировк[аи]\s*\d+\s*[—\-:]\s*(.+)", re.IGNORECASE)


def _today_split(program_content: str | None) -> str:
    if not program_content:
        return "тренировка"
    splits = [m.group(1).strip() for m in _SPLIT_RE.finditer(program_content)]
    if not splits:
        return "тренировка"
    idx = dt.date.today().toordinal() % len(splits)
    return splits[idx]


async def _send_morning(bot: Bot, db: Database, uid: int) -> None:
    profile = await db.get_user(uid)
    if not profile or not profile.get("reminders_enabled"):
        return
    prog = await db.latest_program(uid)
    split = _today_split(prog["content"] if prog else None)
    try:
        await bot.send_message(uid, morning_text(split))
    except Exception as e:  # noqa: BLE001
        logger.warning("не смог отправить утреннее напоминание %s: %s", uid, e)


async def _send_preworkout(bot: Bot, db: Database, uid: int) -> None:
    profile = await db.get_user(uid)
    if not profile or not profile.get("reminders_enabled"):
        return
    try:
        await bot.send_message(uid, "через час зал. уже выпил креатин? разомнись, не лети сразу в рабочий вес.")
    except Exception as e:  # noqa: BLE001
        logger.warning("не смог отправить pre-workout %s: %s", uid, e)


async def _send_checkin(bot: Bot, db: Database, uid: int) -> None:
    profile = await db.get_user(uid)
    if not profile or not profile.get("checkin_enabled"):
        return
    try:
        await bot.send_message(uid, "вечерний чек-ин: как самочувствие? выспался? болит что? пиши /замеры")
    except Exception as e:  # noqa: BLE001
        logger.warning("не смог отправить чек-ин %s: %s", uid, e)


def _parse_hhmm(s: str) -> tuple[int, int]:
    hh, mm = s.split(":")
    return int(hh), int(mm)


def schedule_user(scheduler: AsyncIOScheduler, bot: Bot, db: Database, profile: dict) -> None:
    uid = profile["user_id"]
    for prefix in ("morning", "pre", "checkin"):
        job_id = f"{prefix}:{uid}"
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)

    if not profile.get("reminder_time") or not profile.get("reminders_enabled"):
        return
    tz = profile.get("reminder_tz") or "Europe/Moscow"
    try:
        hh, mm = _parse_hhmm(profile["reminder_time"])
    except Exception:  # noqa: BLE001
        logger.warning("кривое время напоминания у %s: %s", uid, profile.get("reminder_time"))
        return

    scheduler.add_job(
        _send_morning, CronTrigger(hour=hh, minute=mm, timezone=tz),
        args=[bot, db, uid], id=f"morning:{uid}", replace_existing=True,
    )
    pre = (dt.datetime(2000, 1, 1, hh, mm) - dt.timedelta(minutes=45)).time()
    scheduler.add_job(
        _send_preworkout, CronTrigger(hour=pre.hour, minute=pre.minute, timezone=tz),
        args=[bot, db, uid], id=f"pre:{uid}", replace_existing=True,
    )
    if profile.get("checkin_enabled"):
        scheduler.add_job(
            _send_checkin, CronTrigger(hour=21, minute=0, timezone=tz),
            args=[bot, db, uid], id=f"checkin:{uid}", replace_existing=True,
        )


async def schedule_all(scheduler: AsyncIOScheduler, bot: Bot, db: Database) -> None:
    for profile in await db.all_users_with_reminders():
        schedule_user(scheduler, bot, db, profile)
    logger.info("напоминания запланированы")
