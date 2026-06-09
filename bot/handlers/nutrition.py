"""модуль «питание и калории»: учёт еды, норма, свои продукты/блюда, cheat, меню."""
from __future__ import annotations

import json
import logging
import re

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.database.db import Database
from bot.keyboards import cheat_kb
from bot.services.ai import AIUnavailable, ai_service
from bot.services.fatsecret import FatSecretUnavailable, fatsecret_service
from bot.states import CustomFoodFlow, NutritionFlow
from bot.utils.parser import FoodItem, parse_food_line

logger = logging.getLogger(__name__)
router = Router()


async def _require(message: Message, db: Database) -> dict | None:
    profile = await db.get_user(message.from_user.id)
    if not profile or not profile.get("onboarded"):
        await message.answer("сначала онбординг — /start")
        return None
    return profile


def _nums(text: str) -> list[float]:
    return [float(x.replace(",", ".")) for x in re.findall(r"\d+[.,]?\d*", text or "")]


async def _macros_for_item(db: Database, uid: int, item: FoodItem) -> dict | None:
    """ищет макросы продукта: свои продукты -> свои блюда -> fatsecret."""
    food = await db.find_custom_food(uid, item.name)
    if food:
        f = item.grams / 100.0
        return {
            "kcal": food["kcal_100"] * f, "protein": food["protein_100"] * f,
            "fat": food["fat_100"] * f, "carb": food["carb_100"] * f,
        }
    meal = await db.find_custom_meal(uid, item.name)
    if meal:
        # блюдо учитывается как порция целиком (граммовка игнорируется)
        return {"kcal": meal["kcal"], "protein": meal["protein"],
                "fat": meal["fat"], "carb": meal["carb"]}
    try:
        macros = await fatsecret_service.search_food(item.name)
    except FatSecretUnavailable:
        return None
    except Exception as e:  # noqa: BLE001
        logger.warning("fatsecret error: %s", e)
        return None
    if macros:
        f = item.grams / 100.0
        return {
            "kcal": macros.kcal_100 * f, "protein": macros.protein_100 * f,
            "fat": macros.fat_100 * f, "carb": macros.carb_100 * f,
        }
    return None


async def compute_meal(db: Database, uid: int, text: str) -> tuple[dict, list[str], list[str]]:
    items = parse_food_line(text)
    total = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carb": 0.0}
    lines: list[str] = []
    unresolved: list[str] = []
    for item in items:
        macros = await _macros_for_item(db, uid, item)
        if macros is None:
            unresolved.append(item.name)
            continue
        for k in total:
            total[k] += macros[k]
        lines.append(
            f"• {item.name} {item.grams:g}г — {macros['kcal']:.0f} ккал, "
            f"б{macros['protein']:.0f}/ж{macros['fat']:.0f}/у{macros['carb']:.0f}"
        )
    return total, lines, unresolved


def _day_summary(profile: dict, totals: dict) -> str:
    ct = profile.get("calories_target") or 0
    pt = profile.get("protein_target") or 0
    pct = (totals["kcal"] / ct * 100) if ct else 0
    left_kcal = ct - totals["kcal"]
    left_prot = pt - totals["protein"]
    return (
        f"за сегодня: {totals['kcal']:.0f} ккал ({pct:.0f}% нормы), "
        f"белок {totals['protein']:.0f} г, жиры {totals['fat']:.0f} г, "
        f"углеводы {totals['carb']:.0f} г.\n"
        f"осталось {left_kcal:.0f} ккал и {left_prot:.0f} г белка."
    )


@router.message(Command("питание"))
async def cmd_nutrition(message: Message, state: FSMContext, db: Database) -> None:
    profile = await _require(message, db)
    if not profile:
        return
    logs = await db.nutrition_logs(message.from_user.id, log_date=None)
    from bot.database.db import today

    today_logs = [log for log in logs if log["log_date"] == today()]
    totals = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carb": 0.0}
    for log in today_logs:
        for k in totals:
            totals[k] += log[k]
    await message.answer(
        _day_summary(profile, totals) + "\n\nнапиши приём пищи текстом "
        "(напр. «100 г куриной грудки, 200 г гречки») или /стоп."
    )
    await state.set_state(NutritionFlow.meal_text)


@router.message(NutritionFlow.meal_text)
async def nf_meal(message: Message, state: FSMContext, db: Database) -> None:
    data = await state.get_data()
    if data.get("_mode") == "meal" and "=" in (message.text or ""):
        await make_meal(message, state, db)
        return
    text = (message.text or "").strip()
    total, lines, unresolved = await compute_meal(db, message.from_user.id, text)
    if not lines and unresolved:
        await message.answer(
            "ни один продукт не нашёл: " + ", ".join(unresolved) +
            ".\nдобавь свой продукт через /продукт и попробуй снова."
        )
        await state.clear()
        return
    await state.update_data(text=text, total=total)
    msg = "посчитал:\n" + "\n".join(lines)
    msg += (f"\n\nитого: {total['kcal']:.0f} ккал, б{total['protein']:.0f}/"
            f"ж{total['fat']:.0f}/у{total['carb']:.0f}")
    if unresolved:
        msg += "\nне нашёл (пропустил): " + ", ".join(unresolved) + " — добавь через /продукт"
    msg += "\n\nэто обычный приём или cheat?"
    await message.answer(msg, reply_markup=cheat_kb)
    await state.set_state(NutritionFlow.cheat_flag)


@router.callback_query(NutritionFlow.cheat_flag, F.data.startswith("cheat:"))
async def nf_cheat(cb: CallbackQuery, state: FSMContext, db: Database) -> None:
    is_cheat = cb.data.split(":", 1)[1] == "1"
    data = await state.get_data()
    total = data["total"]
    uid = cb.from_user.id
    await db.add_nutrition_log(
        uid, data["text"], total["kcal"], total["protein"], total["fat"], total["carb"], is_cheat
    )
    await state.clear()

    profile = await db.get_user(uid)
    from bot.database.db import today

    logs = [log for log in await db.nutrition_logs(uid) if log["log_date"] == today()]
    day = {"kcal": 0.0, "protein": 0.0, "fat": 0.0, "carb": 0.0}
    for log in logs:
        for k in day:
            day[k] += log[k]

    extra = ""
    if is_cheat:
        ct = profile.get("calories_target") or 0
        over = day["kcal"] - ct
        if over > 0:
            extra = f"\nперелёт на {over:.0f} ккал, завтра готовься сушиться жопой, а не жрать"
        else:
            extra = "\ncheat уложился в норму, молодец, не разросся"
    await cb.message.edit_text("записал." + extra + "\n\n" + _day_summary(profile, day))
    await cb.answer()


# ---------------- свой продукт ----------------
@router.message(Command("продукт"))
async def cmd_food(message: Message, state: FSMContext, db: Database) -> None:
    if not await _require(message, db):
        return
    await message.answer("название продукта? (напр. «мой протеиновый батончик»)")
    await state.set_state(CustomFoodFlow.name)


@router.message(CustomFoodFlow.name)
async def cf_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=(message.text or "").strip())
    await message.answer(
        "введи на 100 г: ккал, белок, жир, углеводы [, порция в г]\n"
        "напр. «380, 30, 12, 40, 60»"
    )
    await state.set_state(CustomFoodFlow.macros)


@router.message(CustomFoodFlow.macros)
async def cf_macros(message: Message, state: FSMContext, db: Database) -> None:
    vals = _nums(message.text or "")
    if len(vals) < 4:
        await message.answer("мало чисел. нужно: ккал, белок, жир, углеводы [, порция]")
        return
    data = await state.get_data()
    portion = vals[4] if len(vals) >= 5 else None
    await db.add_custom_food(
        message.from_user.id, data["name"], vals[0], vals[1], vals[2], vals[3], portion
    )
    await state.clear()
    await message.answer(f"продукт «{data['name']}» сохранён. теперь учитывается в питании.")


# ---------------- меню на день ----------------
@router.message(Command("меню"))
async def cmd_menu(message: Message, db: Database) -> None:
    profile = await _require(message, db)
    if not profile:
        return
    await message.answer("накидываю меню под твою норму, подожди...")
    try:
        menu = await ai_service.generate_menu(profile)
    except AIUnavailable:
        menu = (
            "ии выключен. базовый каркас под норму:\n"
            "- завтрак: овсянка 80г + яйца 3шт + банан\n"
            "- обед: рис 100г + куриная грудка 200г + овощи\n"
            "- перекус: творог 200г + орехи 30г\n"
            "- ужин: говядина/рыба 200г + гречка 100г + салат\n"
            "подгони граммовки под свои цифры. подключи ключ — будет точное меню."
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("ошибка меню")
        menu = f"ии отвалился ({e}). ешь белок, не жри мусор."
    await message.answer(menu)


# ---------------- свои блюда ----------------
@router.message(Command("блюдо"))
async def cmd_meal(message: Message, state: FSMContext, db: Database) -> None:
    if not await _require(message, db):
        return
    await message.answer(
        "опиши блюдо так: «название = ингредиенты».\n"
        "напр. «овсянка с бананом = 80 г овсянки, 1 банан, 20 г арахисового масла»"
    )
    await state.set_state(NutritionFlow.meal_text)
    await state.update_data(_mode="meal")


async def make_meal(message: Message, state: FSMContext, db: Database) -> None:
    name, _, ingredients = (message.text or "").partition("=")
    total, lines, unresolved = await compute_meal(db, message.from_user.id, ingredients)
    if not lines:
        await message.answer("ингредиенты не распознал. добавь продукты через /продукт")
        await state.clear()
        return
    await db.add_custom_meal(
        message.from_user.id, name.strip(), json.dumps(lines, ensure_ascii=False),
        total["kcal"], total["protein"], total["fat"], total["carb"],
    )
    await state.clear()
    note = ("\nне нашёл: " + ", ".join(unresolved)) if unresolved else ""
    await message.answer(
        f"блюдо «{name.strip()}» сохранено: {total['kcal']:.0f} ккал, "
        f"б{total['protein']:.0f}/ж{total['fat']:.0f}/у{total['carb']:.0f}.{note}"
    )
