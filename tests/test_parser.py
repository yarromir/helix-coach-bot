from bot.utils.parser import parse_analysis_text, parse_food_line


def test_parse_food_multiple():
    items = parse_food_line("300 г куриной грудки, 200 г гречки, 50 г сливочного масла")
    assert len(items) == 3
    assert items[0].grams == 300
    assert "куриной грудки" in items[0].name
    assert items[1].grams == 200
    assert items[2].grams == 50


def test_parse_food_kg_and_default():
    items = parse_food_line("1 кг риса")
    assert items[0].grams == 1000
    items2 = parse_food_line("банан")
    assert items2[0].grams == 100


def test_parse_food_trailing_weight():
    items = parse_food_line("пицца маргарита 400 г")
    assert items[0].grams == 400
    assert "пицца" in items[0].name


def test_parse_analysis():
    items = parse_analysis_text("ферритин 8 нг/мл 20-250\nтестостерон 12 нмоль/л 8.6-29")
    assert len(items) == 2
    assert items[0].indicator.startswith("ферритин")
    assert items[0].value == 8
    assert items[0].reference == "20-250"
    assert items[1].value == 12
