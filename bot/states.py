"""состояния FSM (aiogram) для пошаговых сценариев."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Onboarding(StatesGroup):
    goal = State()
    sex = State()
    age = State()
    height = State()
    weight = State()
    level = State()
    equipment = State()
    workouts = State()
    injuries = State()
    program = State()
    reminder = State()
    food = State()


class WorkoutFlow(StatesGroup):
    exercise = State()
    weight = State()
    reps = State()
    sets = State()


class NutritionFlow(StatesGroup):
    meal_text = State()
    cheat_flag = State()


class CustomFoodFlow(StatesGroup):
    name = State()
    macros = State()


class AnalysisFlow(StatesGroup):
    waiting_input = State()
    confirm = State()


class CorrectionFlow(StatesGroup):
    missed = State()
    wellbeing = State()
    complaints = State()


class TechniqueFlow(StatesGroup):
    description = State()


class SettingsFlow(StatesGroup):
    choosing = State()
    value = State()


class MetricFlow(StatesGroup):
    value = State()
