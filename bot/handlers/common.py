"""общие команды: помощь, стоп, главное меню."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.keyboards import main_menu_kb

router = Router()
# отдельный роутер для «всего остального» — подключается последним
fallback_router = Router()

HELP = (
    "команды:\n"
    "/start — онбординг или меню\n"
    "/программа — текущая программа тренировок\n"
    "/тренировка — записать тренировку (пошагово)\n"
    "/техника — разобрать технику по описанию боли\n"
    "/замеры — внести вес тела/замеры/самочувствие\n"
    "/прогресс — графики прогресса\n"
    "/питание — добавить еду / норма и остаток / график калорий\n"
    "/меню — сгенерировать меню на день\n"
    "/продукт — добавить свой продукт\n"
    "/анализы — загрузить анализ / история / графики\n"
    "/коррекция — перестроить программу под самочувствие/боль/пропуски\n"
    "/настройки — напоминания, кол-во тренировок, цель, оборудование\n"
    "/экспорт — выгрузка csv\n"
    "/стоп — отменить текущую операцию\n"
    "/помощь — этот список"
)


@router.message(Command("помощь", "help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP, reply_markup=main_menu_kb)


@router.message(Command("стоп", "stop", "cancel"))
async def cmd_stop(message: Message, state: FSMContext) -> None:
    cur = await state.get_state()
    await state.clear()
    if cur:
        await message.answer("отменил. погнали заново, когда будешь готов.", reply_markup=main_menu_kb)
    else:
        await message.answer("а нечего отменять. качай давай.", reply_markup=main_menu_kb)


@fallback_router.message(StateFilter(None), F.text & ~F.text.startswith("/"))
async def fallback(message: Message) -> None:
    await message.answer(
        "не понял команду. жми /помощь или кнопки меню снизу.", reply_markup=main_menu_kb
    )
