"""генерация ответов бота в нужном стиле + офлайн-фоллбэки без ии.

стиль: грубовато, саркастично, бодибилдерский сленг, всё с маленькой буквы.
фоллбэки используются, когда openai-ключ не задан, чтобы бот не падал.
"""
from __future__ import annotations

import random

from bot.utils.calc import rep_ranges
from bot.utils.parser import AnalysisItem

# ---- справочник российских референсов (приблизительный, для основных показателей) ----
# indicator -> (low, high, units, заметка)
REFERENCES: dict[str, tuple[float, float, str, str]] = {
    "гемоглобин": (130, 170, "г/л", "у качка часто на верхней границе — норм"),
    "ферритин": (30, 250, "нг/мл", "запас железа"),
    "тестостерон": (8.6, 29.0, "нмоль/л", "общий тестостерон"),
    "эстрадиол": (40, 160, "пмоль/л", "следи на курсе/после"),
    "пролактин": (73, 407, "мЕд/л", ""),
    "ттг": (0.4, 4.0, "мкМЕ/мл", "щитовидка"),
    "витамин d": (30, 100, "нг/мл", "ниже 30 — дефицит"),
    "креатинин": (62, 106, "мкмоль/л", "почки/мышечная масса"),
    "лдх": (125, 220, "Ед/л", ""),
    "алт": (0, 45, "Ед/л", "печень"),
    "аст": (0, 35, "Ед/л", "печень"),
    "мочевая кислота": (200, 420, "мкмоль/л", ""),
    "глюкоза": (3.9, 5.9, "ммоль/л", ""),
    "холестерин": (3.0, 5.2, "ммоль/л", ""),
    "кортизол": (140, 640, "нмоль/л", "стресс/перетрен"),
}

# показатели, для которых сильное превышение — это red-flag (к врачу)
CRITICAL_HIGH = {"креатинин": 1.5, "лдх": 1.8, "ттг": 2.5, "алт": 3.0, "аст": 3.0}

_PROGRESS_UP = [
    "жёстко, продолжай в том же духе",
    "вот это движ, не сбавляй",
    "красава, мясо прёт",
]
_PROGRESS_DOWN = [
    "объём просел — значит недоел или завалил сон",
    "слабовато, соберись и доешь белок",
    "откат — не ной, на следующей вытащи",
]
_MORNING = [
    "вставай, блядь, сегодня {split} — время терять жир и наращивать мясо",
    "подъём, {split} сами себя не сделают",
    "хорош дрыхнуть, {split} ждут",
]


def normalize_indicator(name: str) -> str:
    n = name.strip().lower()
    aliases = {
        "витамин д": "витамин d", "тестостерон общий": "тестостерон",
        "т3": "ттг", "холестерол": "холестерин",
    }
    return aliases.get(n, n)


def interpret_analysis(item: AnalysisItem, prev: dict | None = None) -> str:
    """офлайн-расшифровка одного показателя со сравнением с референсом."""
    ind = normalize_indicator(item.indicator)
    ref = REFERENCES.get(ind)
    val = item.value
    if val is None:
        return f"{item.indicator}: значение не распознал, введи вручную"

    trend = ""
    if prev and prev.get("value") is not None:
        diff = val - prev["value"]
        if abs(diff) > 1e-9:
            arrow = "вырос" if diff > 0 else "упал"
            trend = f" (с прошлого раза {arrow} с {prev['value']:g} до {val:g})"

    if not ref:
        return f"{item.indicator} {val:g} — референса нет в базе, гляну глазами{trend}"

    low, high, units, note = ref
    note_s = f", {note}" if note else ""
    if val < low:
        if ind == "ферритин" and val < 15:
            return (f"ферритин {val:g} — это пиздец, ты железо не доедаешь, "
                    f"завались к эндокринологу и сдай трансферрин{trend}")
        return f"{item.indicator} {val:g} {units} — ниже нормы ({low}-{high}){note_s}, подтяни{trend}"
    if val > high:
        crit = CRITICAL_HIGH.get(ind)
        if crit and val > high * crit:
            return (f"внимание, {item.indicator} {val:g} {units} — это серьёзно, "
                    f"завались к врачу завтра же, тяжёлые тренировки отмени до разбора{trend}")
        if ind == "гемоглобин":
            return f"гемоглобин {val:g} — выше нормы, не переживай, это у качка может быть{trend}"
        if ind == "кортизол":
            return (f"кортизол высокий ({val:g}) — перетренированность, спасайся сном "
                    f"или снижай объём недели на 40%{trend}")
        return f"{item.indicator} {val:g} {units} — выше нормы ({low}-{high}){note_s}{trend}"
    return f"{item.indicator} {val:g} {units} — в норме ({low}-{high}), продолжай качать{trend}"


def is_critical(item: AnalysisItem) -> bool:
    ind = normalize_indicator(item.indicator)
    ref = REFERENCES.get(ind)
    crit = CRITICAL_HIGH.get(ind)
    if not ref or crit is None or item.value is None:
        return False
    return item.value > ref[1] * crit


def progress_comment(delta: float) -> str:
    return random.choice(_PROGRESS_UP if delta >= 0 else _PROGRESS_DOWN)


def morning_text(split: str) -> str:
    return random.choice(_MORNING).format(split=split)


# ---- офлайн-генератор программы (фоллбэк без ии) ----
_SPLITS = {
    2: ["верх тела", "низ тела"],
    3: ["грудь + трицепс", "спина + бицепс", "ноги + плечи"],
    4: ["грудь + трицепс", "спина + бицепс", "ноги", "плечи + пресс"],
    5: ["грудь", "спина", "ноги", "плечи + пресс", "руки"],
    6: ["грудь", "спина", "ноги", "плечи", "руки", "пресс + икры"],
}

_EXERCISES: dict[str, list[str]] = {
    "грудь": ["жим штанги лёжа", "жим гантелей на наклонной", "разводка гантелей", "отжимания на брусьях"],
    "спина": ["подтягивания", "тяга штанги в наклоне", "тяга верхнего блока", "тяга горизонтального блока"],
    "ноги": ["приседания со штангой", "жим ногами", "румынская тяга", "выпады с гантелями", "разгибания ног"],
    "плечи": ["жим штанги стоя", "махи гантелями в стороны", "тяга к подбородку", "обратная разводка"],
    "трицепс": ["французский жим", "разгибания на блоке", "жим узким хватом"],
    "бицепс": ["подъём штанги на бицепс", "молотки с гантелями", "подъём на скамье скотта"],
    "руки": ["подъём штанги на бицепс", "французский жим", "молотки", "разгибания на блоке"],
    "пресс": ["скручивания", "подъём ног в висе", "планка"],
    "верх тела": ["жим штанги лёжа", "тяга штанги в наклоне", "жим штанги стоя", "подтягивания", "подъём штанги на бицепс"],
    "низ тела": ["приседания со штангой", "румынская тяга", "жим ногами", "выпады", "подъёмы на носки"],
    "икры": ["подъёмы на носки стоя", "подъёмы на носки сидя"],
}


def _exercises_for(day_name: str) -> list[str]:
    pool: list[str] = []
    for key, exs in _EXERCISES.items():
        if key in day_name:
            pool.extend(exs)
    if not pool:
        pool = _EXERCISES["верх тела"]
    return pool[:5]


def fallback_program(goal: str, workouts_per_week: int, injuries: str | None) -> str:
    wpw = max(2, min(6, int(workouts_per_week or 3)))
    days = _SPLITS.get(wpw, _SPLITS[3])
    rng = rep_ranges("cut" if goal == "cut" else goal)
    inj = (injuries or "").lower()
    lines = ["программа (базовый шаблон, без ии) залита. смотри:\n"]
    for i, day in enumerate(days, 1):
        lines.append(f"тренировка {i} — {day}")
        for j, ex in enumerate(_exercises_for(day), 1):
            ex_name = ex
            if ("спин" in inj) and ("становая" in ex or "румынская" in ex):
                ex_name = "тяга верхнего блока (щадим спину)"
            if ("колен" in inj) and "приседания" in ex:
                ex_name = "жим ногами (щадим колени)"
            lines.append(f"{j}. {ex_name} — 4х{rng['reps']}, отдых {rng['rest']}")
        lines.append("")
    lines.append("это шаблон. подключи openai-ключ — будет уникальная программа под тебя.")
    return "\n".join(lines)
