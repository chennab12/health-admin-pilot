from datetime import date, time

import pytest

import calculations as calc


def test_unit_conversions_round_trip():
    assert calc.lb_to_kg(220.462262185) == pytest.approx(100.0)
    assert calc.kg_to_lb(1) == pytest.approx(2.20462, abs=1e-5)
    assert calc.in_to_cm(1) == 2.54
    assert calc.cm_to_in(254) == pytest.approx(100.0)
    assert calc.ft_in_to_cm(5, 10) == pytest.approx(177.8)
    assert calc.to_kg(10, "kg") == 10
    assert calc.to_cm(10, "in") == pytest.approx(25.4)
    with pytest.raises(ValueError):
        calc.to_kg(10, "stone")


def test_bmi_metric_and_imperial_agree():
    assert calc.bmi(70, 175) == pytest.approx(22.857, abs=1e-3)
    # 154.3 lb, 68.9 in is the same person in imperial units
    assert calc.bmi_imperial(calc.kg_to_lb(70), calc.cm_to_in(175)) == pytest.approx(calc.bmi(70, 175))
    # Classic check: 150 lb at 5 ft 5 in = 25.0
    assert calc.bmi_imperial(150, 65) == pytest.approx(24.96, abs=0.01)


@pytest.mark.parametrize("weight,height", [(0, 170), (70, 10), (500, 170)])
def test_bmi_rejects_impossible_inputs(weight, height):
    with pytest.raises(ValueError):
        calc.bmi(weight, height)


@pytest.mark.parametrize("value,label", [(18.4, "Underweight range"), (18.5, "Healthy weight range"),
                                         (24.99, "Healthy weight range"), (25.0, "Overweight range"),
                                         (30.0, "Obesity range")])
def test_adult_bmi_categories_boundaries(value, label):
    assert calc.adult_bmi_category(value, 35, False)[0] == label


def test_bmi_categories_not_applied_to_children_teens_or_pregnancy():
    for age in (5, 15, 19):
        cat, why = calc.adult_bmi_category(31, age, False)
        assert cat is None and "percentile" in why
    cat, why = calc.adult_bmi_category(31, 30, True)
    assert cat is None and "pregnancy" in why
    assert calc.adult_bmi_category(31, None, False)[0] is None


def test_waist_to_height_is_a_ratio_and_checks_units():
    assert calc.waist_to_height(85, 170) == pytest.approx(0.5)
    assert calc.waist_to_height(34, 68) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        calc.waist_to_height(34, 170)  # inches vs cm mixed up
    with pytest.raises(ValueError):
        calc.waist_to_height(0, 170)


def test_sleep_across_midnight():
    assert calc.sleep_hours("23:30", "06:45") == pytest.approx(7.25)
    assert calc.sleep_hours("22:00", "06:00") == pytest.approx(8.0)
    assert calc.sleep_hours("00:30", "07:00") == pytest.approx(6.5)  # bedtime after midnight
    assert calc.sleep_hours("13:00", "14:30") == pytest.approx(1.5)  # nap, same day
    assert calc.sleep_hours(time(23, 0), time(23, 0)) == pytest.approx(24.0)
    assert calc.sleep_hours("11:15 pm", "6:15 am") == pytest.approx(7.0)


def test_sleep_bad_clock_values():
    with pytest.raises(ValueError):
        calc.sleep_hours("25:00", "06:00")
    with pytest.raises(ValueError):
        calc.sleep_hours(None, "06:00")


def test_bedtime_axis_keeps_after_midnight_later():
    assert calc.bedtime_axis_hours("23:30") == 23.5
    assert calc.bedtime_axis_hours("00:30") == 24.5
    assert calc.clock_label(24.5) == "00:30"


def test_sleep_reference_by_age():
    assert calc.sleep_reference(40)[1:] == (7, None)
    assert calc.sleep_reference(15)[1:] == (8, 10)
    assert calc.sleep_reference(70)[1:] == (7, 8)
    assert calc.sleep_reference(0.5) is None


def test_weekly_activity_blank_days_are_not_zero():
    res = calc.weekly_activity([30, None, 20, "", 40, None, None], 150)
    assert res["total"] == 90
    assert res["days_logged"] == 3 and res["days_not_logged"] == 4
    assert res["progress"] == pytest.approx(0.6)
    assert calc.weekly_activity([None] * 7, None)["progress"] is None
    with pytest.raises(ValueError):
        calc.weekly_activity([2000], 150)
    with pytest.raises(ValueError):
        calc.weekly_activity([10], 0)


def test_completion_percent():
    assert calc.completion_percent(5, 7) == pytest.approx(71.43, abs=0.01)
    assert calc.completion_percent(0, 3) == 0
    for done, planned in ((1, 0), (-1, 5), (8, 7)):
        with pytest.raises(ValueError):
            calc.completion_percent(done, planned)


def test_gentle_progression_caps():
    assert calc.progression_plan(20, 5, 30, weeks=4) == [20, 25, 30, 30]
    assert calc.progression_plan(20, 0, 20, weeks=2) == [20, 20]
    with pytest.raises(ValueError):
        calc.progression_plan(20, 5, 10)
    start = date(2026, 1, 5)
    assert calc.template_minutes(25, 5, 40, start, date(2026, 1, 11)) == 25
    assert calc.template_minutes(25, 5, 40, start, date(2026, 1, 19)) == 35
    assert calc.template_minutes(25, 5, 40, start, date(2026, 6, 1)) == 40
    assert calc.template_minutes(25, 5, 40, None, date(2026, 6, 1)) == 25
