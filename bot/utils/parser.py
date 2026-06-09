"""парсинг текстового ввода: приёмы пищи и результаты анализов."""
from __future__ import annotations

import re
from dataclasses import dataclass

# единицы веса/объёма -> множитель к граммам (объём считаем как граммы, ~вода)
_UNIT_TO_G = {
    "г": 1.0, "гр": 1.0, "грамм": 1.0, "граммов": 1.0, "g": 1.0,
    "кг": 1000.0, "kg": 1000.0,
    "мл": 1.0, "ml": 1.0, "л": 1000.0,
}

# "100 г куриной грудки" / "200г гречки" / "пицца 400 г" / "банан"
_QTY_RE = re.compile(
    r"(?P<qty>\d+[.,]?\d*)\s*(?P<unit>кг|kg|г|гр|грамм(?:ов)?|g|мл|ml|л)\b",
    re.IGNORECASE,
)


@dataclass
class FoodItem:
    name: str
    grams: float


def _to_float(s: str) -> float:
    return float(s.replace(",", "."))


def parse_food_line(text: str) -> list[FoodItem]:
    """разбирает строку питания в список (название, граммы).

    поддерживает: "100 г куриной грудки, 200 г гречки, 50 г масла",
    "пицца маргарита 400 г", "банан" (по умолчанию 100 г).
    """
    items: list[FoodItem] = []
    for chunk in re.split(r"[,;]|\bи\b|\+|\n", text):
        chunk = chunk.strip()
        if not chunk:
            continue
        m = _QTY_RE.search(chunk)
        if m:
            grams = _to_float(m.group("qty")) * _UNIT_TO_G.get(m.group("unit").lower(), 1.0)
            name = (chunk[: m.start()] + " " + chunk[m.end():]).strip(" -—.,")
        else:
            grams = 100.0
            name = chunk.strip(" -—.,")
        name = re.sub(r"\s+", " ", name).strip().lower()
        if name:
            items.append(FoodItem(name=name, grams=grams))
    return items


@dataclass
class AnalysisItem:
    indicator: str
    value: float | None
    units: str | None
    reference: str | None


# строка анализа: "ферритин 8 нг/мл 20-250" / "тестостерон: 12 нмоль/л (8.6-29)"
_REF_RE = re.compile(r"(\d+[.,]?\d*)\s*[-–—]\s*(\d+[.,]?\d*)")
_VALUE_RE = re.compile(r"(-?\d+[.,]?\d*)")
_UNIT_RE = re.compile(
    r"(нг/мл|нмоль/л|пмоль/л|мкг/л|мкмоль/л|ммоль/л|мкмЕ/мл|мЕд/л|мкг/дл|г/л|г/дл|"
    r"ед/л|u/l|пг/мл|%|нг/дл|мг/дл|10\^?\d+)",
    re.IGNORECASE,
)


def parse_analysis_text(text: str) -> list[AnalysisItem]:
    """разбирает ручной ввод анализов: одна строка — один показатель."""
    items: list[AnalysisItem] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        ref = None
        ref_m = _REF_RE.search(line)
        if ref_m:
            ref = f"{ref_m.group(1)}-{ref_m.group(2)}"
            line_wo_ref = line[: ref_m.start()] + line[ref_m.end():]
        else:
            line_wo_ref = line

        unit = None
        unit_m = _UNIT_RE.search(line_wo_ref)
        if unit_m:
            unit = unit_m.group(1)
            line_wo_ref = line_wo_ref[: unit_m.start()] + line_wo_ref[unit_m.end():]

        # имя показателя — текст до первого числа
        name_m = re.match(r"\s*([^\d:=]+)", line_wo_ref)
        indicator = (name_m.group(1).strip(" :=-—.") if name_m else line).lower()

        value = None
        rest = line_wo_ref[name_m.end():] if name_m else line_wo_ref
        val_m = _VALUE_RE.search(rest)
        if val_m:
            value = _to_float(val_m.group(1))

        if indicator:
            items.append(
                AnalysisItem(indicator=indicator, value=value, units=unit, reference=ref)
            )
    return items
