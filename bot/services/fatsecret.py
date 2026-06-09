"""обёртка для fatsecret api (oauth2 client credentials).

если ключи не заданы — кидаем FatSecretUnavailable, бот предложит ручной ввод.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass

import httpx

from bot.config import config

logger = logging.getLogger(__name__)

TOKEN_URL = "https://oauth.fatsecret.com/connect/token"
API_URL = "https://platform.fatsecret.com/rest/server.api"

# "Per 100g - Calories: 165kcal | Fat: 3.57g | Carbs: 0g | Protein: 31g"
# "Per 1 serving (28g) - Calories: ..."
_DESC_RE = re.compile(
    r"Per\s+(?P<portion>[^-]+?)\s*-\s*Calories:\s*(?P<kcal>[\d.]+)kcal\s*\|\s*"
    r"Fat:\s*(?P<fat>[\d.]+)g\s*\|\s*Carbs:\s*(?P<carb>[\d.]+)g\s*\|\s*"
    r"Protein:\s*(?P<protein>[\d.]+)g",
    re.IGNORECASE,
)
_GRAMS_RE = re.compile(r"(\d+[.,]?\d*)\s*g", re.IGNORECASE)


class FatSecretUnavailable(RuntimeError):
    pass


@dataclass
class FoodMacros:
    name: str
    kcal_100: float
    protein_100: float
    fat_100: float
    carb_100: float


def _parse_description(name: str, desc: str) -> FoodMacros | None:
    m = _DESC_RE.search(desc)
    if not m:
        return None
    kcal = float(m.group("kcal"))
    fat = float(m.group("fat"))
    carb = float(m.group("carb"))
    protein = float(m.group("protein"))
    portion = m.group("portion").strip().lower()

    # привести к 100 г
    if "100g" in portion.replace(" ", ""):
        factor = 1.0
    else:
        gm = _GRAMS_RE.search(portion)
        grams = float(gm.group(1).replace(",", ".")) if gm else None
        factor = 100.0 / grams if grams else 1.0
    return FoodMacros(
        name=name,
        kcal_100=round(kcal * factor, 1),
        protein_100=round(protein * factor, 1),
        fat_100=round(fat * factor, 1),
        carb_100=round(carb * factor, 1),
    )


class FatSecretService:
    def __init__(self) -> None:
        self._token: str | None = None
        self._token_exp: float = 0.0

    @property
    def enabled(self) -> bool:
        return config.fatsecret_enabled

    async def _get_token(self) -> str:
        if not self.enabled:
            raise FatSecretUnavailable("ключи fatsecret не заданы")
        if self._token and time.time() < self._token_exp - 30:
            return self._token
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials", "scope": "basic"},
                auth=(config.fatsecret_client_id, config.fatsecret_client_secret),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            data = resp.json()
        self._token = data["access_token"]
        self._token_exp = time.time() + int(data.get("expires_in", 3600))
        return self._token

    async def search_food(self, query: str) -> FoodMacros | None:
        """ищет продукт и возвращает макросы на 100 г (лучшее совпадение)."""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                API_URL,
                params={
                    "method": "foods.search",
                    "search_expression": query,
                    "format": "json",
                    "max_results": 5,
                },
                headers={"Authorization": f"Bearer {token}"},
            )
            resp.raise_for_status()
            data = resp.json()

        foods = (data.get("foods") or {}).get("food")
        if not foods:
            return None
        if isinstance(foods, dict):
            foods = [foods]
        for food in foods:
            macros = _parse_description(
                food.get("food_name", query), food.get("food_description", "")
            )
            if macros:
                return macros
        return None


fatsecret_service = FatSecretService()
