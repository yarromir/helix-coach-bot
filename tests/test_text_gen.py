from bot.utils.parser import AnalysisItem
from bot.utils.text_gen import fallback_program, interpret_analysis, is_critical


def test_interpret_low_ferritin():
    item = AnalysisItem(indicator="ферритин", value=8, units="нг/мл", reference="20-250")
    text = interpret_analysis(item)
    assert "железо" in text.lower()


def test_interpret_normal_testosterone():
    item = AnalysisItem(indicator="тестостерон", value=18, units="нмоль/л", reference=None)
    text = interpret_analysis(item)
    assert "норм" in text.lower()


def test_critical_creatinine():
    item = AnalysisItem(indicator="креатинин", value=180, units="мкмоль/л", reference=None)
    assert is_critical(item) is True
    item2 = AnalysisItem(indicator="креатинин", value=90, units="мкмоль/л", reference=None)
    assert is_critical(item2) is False


def test_trend_comparison():
    item = AnalysisItem(indicator="тестостерон", value=18, units="нмоль/л", reference=None)
    text = interpret_analysis(item, prev={"value": 14})
    assert "вырос" in text


def test_fallback_program_respects_workouts():
    prog = fallback_program("mass", 3, "нет ограничений")
    assert "тренировка 1" in prog
    assert "тренировка 3" in prog
    assert "тренировка 4" not in prog
