"""обёртка для llm (openai). промпты жёстко регламентированы.

если ключ не задан — методы кидают AIUnavailable, вызывающий код использует
офлайн-фоллбэк из utils.text_gen.
"""
from __future__ import annotations

import logging

from bot.config import config

logger = logging.getLogger(__name__)

SYSTEM_STYLE = (
    "ты — персональный бодибилдинг-тренер для опытного атлета. общаешься на русском. "
    "тон грубоватый, саркастичный, но поддерживающий; бодибилдерский сленг, "
    "мат уместен и естественен. все предложения начинай с маленькой буквы. "
    "без медицинского официоза, кратко и по делу."
)


class AIUnavailable(RuntimeError):
    pass


class AIService:
    def __init__(self) -> None:
        self._client = None
        if config.ai_enabled:
            try:
                from openai import AsyncOpenAI

                kwargs = {"api_key": config.openai_api_key}
                if config.openai_base_url:
                    kwargs["base_url"] = config.openai_base_url
                self._client = AsyncOpenAI(**kwargs)
            except Exception as e:  # noqa: BLE001
                logger.warning("не удалось инициализировать openai: %s", e)
                self._client = None

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def _chat(self, user_prompt: str, system: str = SYSTEM_STYLE) -> str:
        if self._client is None:
            raise AIUnavailable("openai-ключ не задан")
        logger.info("llm запрос: %s...", user_prompt[:80])
        resp = await self._client.chat.completions.create(
            model=config.openai_model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.8,
        )
        return (resp.choices[0].message.content or "").strip()

    async def generate_program(self, profile: dict) -> str:
        prompt = (
            f"опыт атлета: {profile.get('level')}. цель: {profile.get('goal')}. "
            f"оборудование: {profile.get('equipment')}. "
            f"количество тренировок в неделю: {profile.get('workouts_per_week')}. "
            f"травмы/ограничения: {profile.get('injuries') or 'нет'}. "
            f"текущая программа: {profile.get('current_program') or 'нет'}.\n\n"
            f"сгенерируй программу тренировок на {profile.get('cycle_weeks', 4)} недели.\n"
            "требования:\n"
            "- сплит под количество тренировок в неделю.\n"
            "- каждое упражнение под доступное оборудование (нет скамьи — только свободные).\n"
            "- для каждой тренировки: название, упражнения с подходами, повторениями, отдыхом "
            "и кратким комментарием по технике (1–2 предложения).\n"
            "- учитывай травмы: спина — без становой и гакк-машины, замена на тяги блоками; "
            "колени — без глубоких приседаний.\n"
            "- используй сленг, но кратко. без медицинского официоза."
        )
        return await self._chat(prompt)

    async def adjust_program(
        self, profile: dict, missed_days: int, wellbeing: str, complaints: str
    ) -> str:
        prompt = (
            f"профиль: цель {profile.get('goal')}, уровень {profile.get('level')}, "
            f"оборудование {profile.get('equipment')}, "
            f"{profile.get('workouts_per_week')} тренировок/неделю.\n"
            f"пользователь пропустил {missed_days} дней. самочувствие: {wellbeing or 'не указано'}. "
            f"жалобы: {complaints or 'нет'}.\n\n"
            "скорректируй ближайшую тренировку:\n"
            "- если пропуск >3 дней — снизь объём на 30%, добавь разогрев.\n"
            "- если боль в спине/коленях/плечах — замени ударные упражнения на щадящие.\n"
            "- верни конкретную тренировку с упражнениями, подходами, повторениями и отдыхом."
        )
        return await self._chat(prompt)

    async def interpret_analyses(self, table: str, history: str = "") -> str:
        prompt = (
            "результаты анализов (показатель, значение, единицы, референс):\n"
            f"{table}\n\n"
            + (f"исторические данные:\n{history}\n\n" if history else "")
            + "раскладка:\n"
            "- по каждому показателю сравни с референсом.\n"
            "- незначительное отклонение — пошути, что у атлета это норма.\n"
            "- существенное — краткий вывод и совет.\n"
            "- критическое — красный флаг и рекомендация срочно к врачу.\n"
            "- если есть история — отметь тренд."
        )
        return await self._chat(prompt)

    async def generate_menu(self, profile: dict) -> str:
        prompt = (
            f"цель: {profile.get('goal')}. норма: {profile.get('calories_target')} ккал, "
            f"белок {profile.get('protein_target')} г, жиры {profile.get('fat_target')} г, "
            f"углеводы {profile.get('carb_target')} г.\n"
            f"не ест/ненавидит: {profile.get('food_dislikes') or 'нет ограничений'}.\n\n"
            "составь примерное меню на день под эту норму и предпочтения. "
            "укажи блюда и примерные граммовки, уложись в норму. кратко."
        )
        return await self._chat(prompt)

    async def fix_technique(self, description: str) -> str:
        prompt = (
            f"атлет жалуется на технику/боль: «{description}».\n"
            "определи типичную ошибку и дай грубоватое короткое исправление. "
            "если непонятно что и где болит — попроси уточнить."
        )
        return await self._chat(prompt)


ai_service = AIService()
