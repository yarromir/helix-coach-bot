"""асинхронный слой доступа к sqlite через aiosqlite."""
from __future__ import annotations

import datetime as dt
from typing import Any

import aiosqlite

from bot.database.models import SCHEMA

# поля профиля, которые можно безопасно обновлять через update_user
USER_FIELDS = {
    "username", "goal", "sex", "age", "height", "weight", "level", "equipment",
    "workouts_per_week", "injuries", "current_program", "reminder_time", "reminder_tz",
    "food_dislikes", "cycle_weeks", "reminders_enabled", "checkin_enabled",
    "calories_target", "protein_target", "fat_target", "carb_target", "onboarded",
}


def today() -> str:
    return dt.date.today().isoformat()


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("база не инициализирована — вызови connect()")
        return self._conn

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ----- users -----
    async def ensure_user(self, user_id: int, username: str | None = None) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)",
            (user_id, username),
        )
        await self.conn.commit()

    async def get_user(self, user_id: int) -> dict[str, Any] | None:
        cur = await self.conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = await cur.fetchone()
        return dict(row) if row else None

    async def update_user(self, user_id: int, **fields: Any) -> None:
        clean = {k: v for k, v in fields.items() if k in USER_FIELDS}
        if not clean:
            return
        cols = ", ".join(f"{k} = ?" for k in clean)
        params = list(clean.values()) + [user_id]
        await self.conn.execute(
            f"UPDATE users SET {cols}, updated_at = datetime('now') WHERE user_id = ?",
            params,
        )
        await self.conn.commit()

    async def all_users_with_reminders(self) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE onboarded = 1 AND reminders_enabled = 1 "
            "AND reminder_time IS NOT NULL"
        )
        return [dict(r) for r in await cur.fetchall()]

    # ----- programs -----
    async def save_program(self, user_id: int, content: str, cycle_weeks: int = 4) -> int:
        cur = await self.conn.execute(
            "INSERT INTO programs (user_id, content, cycle_weeks) VALUES (?, ?, ?)",
            (user_id, content, cycle_weeks),
        )
        await self.conn.commit()
        return cur.lastrowid or 0

    async def latest_program(self, user_id: int) -> dict[str, Any] | None:
        cur = await self.conn.execute(
            "SELECT * FROM programs WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        )
        row = await cur.fetchone()
        return dict(row) if row else None

    # ----- workout logs -----
    async def add_workout_log(
        self, user_id: int, exercise: str, weight: float, reps: int, sets: int,
        log_date: str | None = None,
    ) -> None:
        volume = weight * reps * sets
        await self.conn.execute(
            "INSERT INTO workout_logs (user_id, log_date, exercise, weight, reps, sets, volume) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, log_date or today(), exercise, weight, reps, sets, volume),
        )
        await self.conn.commit()

    async def workout_logs(self, user_id: int, limit: int | None = None) -> list[dict[str, Any]]:
        sql = "SELECT * FROM workout_logs WHERE user_id = ? ORDER BY log_date, id"
        params: list[Any] = [user_id]
        if limit:
            sql += " DESC LIMIT ?"
            params.append(limit)
        cur = await self.conn.execute(sql, params)
        return [dict(r) for r in await cur.fetchall()]

    async def exercise_history(self, user_id: int, exercise: str) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM workout_logs WHERE user_id = ? AND exercise = ? ORDER BY log_date, id",
            (user_id, exercise),
        )
        return [dict(r) for r in await cur.fetchall()]

    # ----- body metrics -----
    async def add_body_metric(self, user_id: int, **fields: Any) -> None:
        allowed = {"weight", "chest", "waist", "hips", "biceps", "wellbeing", "comment"}
        data = {k: v for k, v in fields.items() if k in allowed}
        data["user_id"] = user_id
        data["log_date"] = fields.get("log_date", today())
        cols = ", ".join(data)
        ph = ", ".join("?" for _ in data)
        await self.conn.execute(
            f"INSERT INTO body_metrics ({cols}) VALUES ({ph})", list(data.values())
        )
        await self.conn.commit()

    async def body_metrics(self, user_id: int) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM body_metrics WHERE user_id = ? ORDER BY log_date, id", (user_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    # ----- custom foods / meals -----
    async def add_custom_food(
        self, user_id: int, name: str, kcal_100: float, protein_100: float,
        fat_100: float, carb_100: float, portion_g: float | None = None,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO custom_foods (user_id, name, kcal_100, protein_100, fat_100, "
            "carb_100, portion_g) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, name.lower().strip(), kcal_100, protein_100, fat_100, carb_100, portion_g),
        )
        await self.conn.commit()

    async def find_custom_food(self, user_id: int, name: str) -> dict[str, Any] | None:
        from bot.utils.match import fuzzy_find

        cur = await self.conn.execute(
            "SELECT * FROM custom_foods WHERE user_id = ? AND name = ? ORDER BY id DESC LIMIT 1",
            (user_id, name.lower().strip()),
        )
        row = await cur.fetchone()
        if row:
            return dict(row)
        # нечёткий поиск по складам/опечаткам
        foods = await self.list_custom_foods(user_id)
        match = fuzzy_find(name, [f["name"] for f in foods])
        if match:
            for f in reversed(foods):
                if f["name"] == match:
                    return f
        return None

    async def list_custom_foods(self, user_id: int) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT * FROM custom_foods WHERE user_id = ? ORDER BY name", (user_id,)
        )
        return [dict(r) for r in await cur.fetchall()]

    async def add_custom_meal(
        self, user_id: int, name: str, items_json: str,
        kcal: float, protein: float, fat: float, carb: float,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO custom_meals (user_id, name, items_json, kcal, protein, fat, carb) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, name.lower().strip(), items_json, kcal, protein, fat, carb),
        )
        await self.conn.commit()

    async def find_custom_meal(self, user_id: int, name: str) -> dict[str, Any] | None:
        from bot.utils.match import fuzzy_find

        cur = await self.conn.execute(
            "SELECT * FROM custom_meals WHERE user_id = ? AND name = ? ORDER BY id DESC LIMIT 1",
            (user_id, name.lower().strip()),
        )
        row = await cur.fetchone()
        if row:
            return dict(row)
        cur = await self.conn.execute(
            "SELECT * FROM custom_meals WHERE user_id = ? ORDER BY id DESC", (user_id,)
        )
        meals = [dict(r) for r in await cur.fetchall()]
        match = fuzzy_find(name, [m["name"] for m in meals])
        if match:
            for m in meals:
                if m["name"] == match:
                    return m
        return None

    # ----- nutrition logs -----
    async def add_nutrition_log(
        self, user_id: int, description: str, kcal: float, protein: float,
        fat: float, carb: float, is_cheat: bool = False, log_date: str | None = None,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO nutrition_logs (user_id, log_date, description, kcal, protein, fat, "
            "carb, is_cheat) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (user_id, log_date or today(), description, kcal, protein, fat, carb, int(is_cheat)),
        )
        await self.conn.commit()

    async def nutrition_logs(
        self, user_id: int, log_date: str | None = None
    ) -> list[dict[str, Any]]:
        if log_date is not None:
            cur = await self.conn.execute(
                "SELECT * FROM nutrition_logs WHERE user_id = ? AND log_date = ? ORDER BY id",
                (user_id, log_date),
            )
        else:
            cur = await self.conn.execute(
                "SELECT * FROM nutrition_logs WHERE user_id = ? ORDER BY log_date, id", (user_id,)
            )
        return [dict(r) for r in await cur.fetchall()]

    async def nutrition_daily_totals(self, user_id: int) -> list[dict[str, Any]]:
        cur = await self.conn.execute(
            "SELECT log_date, SUM(kcal) kcal, SUM(protein) protein, SUM(fat) fat, "
            "SUM(carb) carb FROM nutrition_logs WHERE user_id = ? GROUP BY log_date "
            "ORDER BY log_date",
            (user_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    # ----- analyses -----
    async def add_analysis(
        self, user_id: int, indicator: str, value: float | None, units: str | None,
        reference: str | None, interpretation: str | None, log_date: str | None = None,
    ) -> None:
        await self.conn.execute(
            "INSERT INTO analyses (user_id, log_date, indicator, value, units, reference, "
            "interpretation) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, log_date or today(), indicator, value, units, reference, interpretation),
        )
        await self.conn.commit()

    async def analyses(
        self, user_id: int, indicator: str | None = None
    ) -> list[dict[str, Any]]:
        if indicator is not None:
            cur = await self.conn.execute(
                "SELECT * FROM analyses WHERE user_id = ? AND indicator = ? ORDER BY log_date, id",
                (user_id, indicator),
            )
        else:
            cur = await self.conn.execute(
                "SELECT * FROM analyses WHERE user_id = ? ORDER BY log_date, id", (user_id,)
            )
        return [dict(r) for r in await cur.fetchall()]

    async def previous_analysis(
        self, user_id: int, indicator: str
    ) -> dict[str, Any] | None:
        cur = await self.conn.execute(
            "SELECT * FROM analyses WHERE user_id = ? AND indicator = ? ORDER BY log_date DESC, "
            "id DESC LIMIT 1, 1",
            (user_id, indicator),
        )
        row = await cur.fetchone()
        return dict(row) if row else None
