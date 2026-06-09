from bot.utils.calc import bmr_mifflin, calc_targets, epley_1rm, volume


def test_bmr_mifflin_male():
    # 88кг, 182см, 30 лет -> 10*88 + 6.25*182 - 5*30 + 5 = 1872.5
    assert round(bmr_mifflin("male", 88, 182, 30), 1) == 1872.5


def test_bmr_mifflin_female():
    assert round(bmr_mifflin("female", 60, 165, 25), 1) == round(
        10 * 60 + 6.25 * 165 - 5 * 25 - 161, 1
    )


def test_calc_targets_mass_surplus():
    t = calc_targets("male", 88, 182, 30, "mass", 4)
    assert t.calories > t.tdee  # профицит на массе
    assert t.protein == round(2.0 * 88)
    assert t.fat == round(0.9 * 88)


def test_calc_targets_cut_deficit():
    t = calc_targets("male", 88, 182, 30, "cut", 4)
    assert t.calories < t.tdee  # дефицит на сушке


def test_volume():
    assert volume(100, 8, 4) == 3200


def test_epley_1rm():
    assert epley_1rm(100, 1) == 100
    assert round(epley_1rm(100, 10), 1) == round(100 * (1 + 10 / 30), 1)
    assert epley_1rm(100, 0) == 0
