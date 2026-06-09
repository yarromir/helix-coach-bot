"""расчёты: норма калорий/бжу (миффлин — сан жеор), объём, 1rm (эпли)."""
from __future__ import annotations

from dataclasses import dataclass

# коэффициенты активности по количеству тренировок в неделю
ACTIVITY_BY_WORKOUTS = {
    0: 1.2, 1: 1.3, 2: 1.375, 3: 1.46, 4: 1.55, 5: 1.65, 6: 1.725, 7: 1.9,
}

# корректировка калорий по цели
GOAL_KCAL_ADJUST = {"mass": 400, "cut": -400, "maintain": 0}

# белок (г/кг) по цели
PROTEIN_PER_KG = {"mass": 2.0, "cut": 2.2, "maintain": 1.8}
FAT_PER_KG = 0.9


@dataclass
class Targets:
    bmr: float
    tdee: float
    calories: float
    protein: float
    fat: float
    carb: float


def bmr_mifflin(sex: str, weight: float, height: float, age: int) -> float:
    """базовый обмен по формуле миффлина — сан жеора."""
    base = 10 * weight + 6.25 * height - 5 * age
    return base + 5 if sex == "male" else base - 161


def activity_factor(workouts_per_week: int) -> float:
    wpw = max(0, min(7, int(workouts_per_week or 0)))
    return ACTIVITY_BY_WORKOUTS.get(wpw, 1.55)


def calc_targets(
    sex: str, weight: float, height: float, age: int, goal: str, workouts_per_week: int
) -> Targets:
    bmr = bmr_mifflin(sex, weight, height, age)
    tdee = bmr * activity_factor(workouts_per_week)
    calories = tdee + GOAL_KCAL_ADJUST.get(goal, 0)

    protein = PROTEIN_PER_KG.get(goal, 1.8) * weight
    fat = FAT_PER_KG * weight
    kcal_from_pf = protein * 4 + fat * 9
    carb = max(0.0, (calories - kcal_from_pf) / 4)

    return Targets(
        bmr=round(bmr),
        tdee=round(tdee),
        calories=round(calories),
        protein=round(protein),
        fat=round(fat),
        carb=round(carb),
    )


def volume(weight: float, reps: int, sets: int) -> float:
    return weight * reps * sets


def epley_1rm(weight: float, reps: int) -> float:
    """оценка 1ПМ по формуле эпли: w * (1 + reps/30)."""
    if reps <= 0:
        return 0.0
    if reps == 1:
        return weight
    return weight * (1 + reps / 30)


def rep_ranges(goal: str) -> dict[str, str]:
    """диапазон повторений и отдыха под цель — для подсказок."""
    table = {
        "mass": {"reps": "8–12", "rest": "90–120 сек"},
        "strength": {"reps": "3–6", "rest": "180–240 сек"},
        "cut": {"reps": "12–15", "rest": "60–90 сек"},
        "maintain": {"reps": "8–15 (смешанный)", "rest": "60–120 сек"},
    }
    return table.get(goal, table["maintain"])
