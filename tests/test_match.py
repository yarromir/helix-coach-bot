from bot.utils.match import fuzzy_find


def test_declension():
    cands = ["куриная грудка", "гречка", "овсянка"]
    assert fuzzy_find("куриной грудки", cands) == "куриная грудка"
    assert fuzzy_find("гречки", cands) == "гречка"


def test_word_order():
    assert fuzzy_find("масла сливочного", ["сливочное масло", "гречка"]) == "сливочное масло"


def test_no_match():
    assert fuzzy_find("пельмени", ["куриная грудка", "гречка"]) is None
