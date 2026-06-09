"""схема базы данных (sqlite).

схема нормализована, но не переусложнена: один пользователь — много записей
тренировок, питания, анализов и замеров.
"""
from __future__ import annotations

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id            INTEGER PRIMARY KEY,
    username           TEXT,
    goal               TEXT,            -- mass | cut | maintain
    sex                TEXT,            -- male | female
    age                INTEGER,
    height             REAL,            -- см
    weight             REAL,            -- кг
    level              TEXT,            -- novice | medium | advanced | expert
    equipment          TEXT,           -- свободный текст
    workouts_per_week  INTEGER,
    injuries           TEXT,
    current_program    TEXT,
    reminder_time      TEXT,            -- HH:MM
    reminder_tz        TEXT,            -- IANA, напр. Europe/Moscow
    food_dislikes      TEXT,
    cycle_weeks        INTEGER DEFAULT 4,
    reminders_enabled  INTEGER DEFAULT 1,
    checkin_enabled    INTEGER DEFAULT 0,
    calories_target    REAL,
    protein_target     REAL,
    fat_target         REAL,
    carb_target        REAL,
    onboarded          INTEGER DEFAULT 0,
    created_at         TEXT DEFAULT (datetime('now')),
    updated_at         TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS programs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    content     TEXT NOT NULL,
    cycle_weeks INTEGER DEFAULT 4,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS workout_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    log_date    TEXT NOT NULL,         -- YYYY-MM-DD
    exercise    TEXT NOT NULL,
    weight      REAL NOT NULL,
    reps        INTEGER NOT NULL,
    sets        INTEGER NOT NULL,
    volume      REAL NOT NULL,         -- weight * reps * sets
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS body_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    log_date    TEXT NOT NULL,
    weight      REAL,
    chest       REAL,
    waist       REAL,
    hips        REAL,
    biceps      REAL,
    wellbeing   INTEGER,               -- 1..5
    comment     TEXT,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS custom_foods (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    name        TEXT NOT NULL,
    kcal_100    REAL NOT NULL,
    protein_100 REAL NOT NULL,
    fat_100     REAL NOT NULL,
    carb_100    REAL NOT NULL,
    portion_g   REAL,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS custom_meals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    name        TEXT NOT NULL,
    items_json  TEXT NOT NULL,         -- список ингредиентов
    kcal        REAL NOT NULL,
    protein     REAL NOT NULL,
    fat         REAL NOT NULL,
    carb        REAL NOT NULL,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS nutrition_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    log_date    TEXT NOT NULL,
    description TEXT NOT NULL,
    kcal        REAL NOT NULL,
    protein     REAL NOT NULL,
    fat         REAL NOT NULL,
    carb        REAL NOT NULL,
    is_cheat    INTEGER DEFAULT 0,
    created_at  TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE TABLE IF NOT EXISTS analyses (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    log_date       TEXT NOT NULL,
    indicator      TEXT NOT NULL,
    value          REAL,
    units          TEXT,
    reference      TEXT,
    interpretation TEXT,
    created_at     TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

CREATE INDEX IF NOT EXISTS idx_workout_user_date ON workout_logs(user_id, log_date);
CREATE INDEX IF NOT EXISTS idx_nutrition_user_date ON nutrition_logs(user_id, log_date);
CREATE INDEX IF NOT EXISTS idx_analyses_user_ind ON analyses(user_id, indicator);
CREATE INDEX IF NOT EXISTS idx_metrics_user_date ON body_metrics(user_id, log_date);
"""

# человекочитаемые названия для перечислений
GOALS = {"mass": "набор массы", "cut": "похудение", "maintain": "поддержка формы"}
SEXES = {"male": "мужской", "female": "женский"}
LEVELS = {
    "novice": "новичок (<1 года)",
    "medium": "средний (1–3 года)",
    "advanced": "продвинутый (3–5 лет)",
    "expert": "эксперт (>5 лет)",
}
