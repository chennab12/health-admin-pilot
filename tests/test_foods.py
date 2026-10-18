import pytest

import foods
import sources


def test_dataset_rows_are_complete_and_sourced():
    assert len(foods.FOODS) >= 15
    for f in foods.FOODS:
        assert f["fdc_id"] and f["fdc_description"] and f["portion_g"] > 0
        assert all(f[n] is not None and f[n] >= 0 for n in foods.NUTRIENTS)
        # Energy from macros (4/4/9) should be in the same ballpark as listed energy
        est = 4 * f["protein_g"] + 4 * f["carbs_g"] + 9 * f["fat_g"]
        assert abs(est - f["kcal"]) <= 0.2 * f["kcal"] + 10, f["name"]
    assert "fdc.nal.usda.gov" in sources.USDA_FDC["url"]


def test_item_nutrition_scales_by_grams_and_portions():
    banana = foods.food_table()["banana"]
    n = foods.item_nutrition(banana, foods.item_grams(banana, None, 1))  # 1 medium = 118 g
    assert n["kcal"] == pytest.approx(89 * 1.18)
    assert foods.item_grams(banana, 50, 3) == 50  # grams win over portions


def test_missing_data_is_none_not_zero():
    table = foods.food_table([{"name": "Wrap", "kcal": 200, "protein_g": 7, "carbs_g": 30, "fat_g": 7,
                               "fiber_g": None, "portion_g": 150}])
    wrap = table["wrap"]
    n = foods.item_nutrition(wrap, 150)
    assert n["fiber_g"] is None and n["kcal"] == pytest.approx(300)
    assert foods.item_grams(wrap, None, None) is None
    assert all(v is None for v in foods.item_nutrition(None, 100).values())
    rows = foods.meal_log_nutrition([
        {"food": "Banana", "portions": 1}, {"food": "Wrap", "portions": 1},
        {"food": "Mystery stew", "grams": 200}, {"food": "Apple"}], [
        {"name": "Wrap", "kcal": 200, "protein_g": 7, "carbs_g": 30, "fat_g": 7, "fiber_g": None, "portion_g": 150}])
    assert [r["status"] for r in rows] == ["OK", "Some nutrients unknown for this food",
                                           "Food not in dataset: add it under My foods",
                                           "Amount missing: enter grams or portions"]
    tot = foods.total_nutrition(rows)
    assert tot["kcal"]["known"] == 2 and tot["kcal"]["missing"] == 2
    assert tot["fiber_g"]["known"] == 1 and tot["fiber_g"]["missing"] == 3
    assert foods.total_nutrition([{"kcal": None, **{n: None for n in foods.NUTRIENTS}}])["kcal"]["total"] is None


def test_recipe_per_serving():
    res = foods.recipe_per_serving([
        {"ingredient": "A", "grams": 200, "kcal": 100, "protein_g": 10, "carbs_g": 10, "fat_g": 1, "fiber_g": 5},
        {"ingredient": "B", "grams": 100, "kcal": 50, "protein_g": 2, "carbs_g": 5, "fat_g": 0, "fiber_g": None},
    ], 2)
    assert res["kcal"]["per_serving"] == pytest.approx(125)
    assert res["fiber_g"]["per_serving"] == pytest.approx(5) and res["fiber_g"]["missing"] == 1
    with pytest.raises(ValueError):
        foods.recipe_per_serving([], 0)
    with pytest.raises(ValueError):
        foods.recipe_per_serving([{"ingredient": "x", "grams": -5, "kcal": 1}], 1)


def test_grocery_list_combines_same_units_only():
    plan = [{"dish": "Oats", "ingredients": "Oats 160 g; Milk 0.5 l; Bananas 2"},
            {"dish": "Bowl", "ingredients": "oats 40 g; Milk 1 cup; Bananas 3; Salsa"}]
    rows = {(r["item"].lower(), r["unit"]): r for r in foods.grocery_list(plan)}
    assert rows[("oats", "g")]["quantity"] == 200
    assert rows[("bananas", "item")]["quantity"] == 5
    assert rows[("milk", "ml")]["quantity"] == 500
    assert rows[("milk", "cup")]["quantity"] == 1
    assert "not converted" in rows[("milk", "cup")]["note"]
    assert rows[("salsa", "")]["quantity"] is None
    assert rows[("oats", "g")]["used_in"] == "Oats, Bowl"


def test_allergy_mentions_is_text_match_only():
    assert foods.allergy_mentions("Yogurt with almonds", ["almond", "peanut"]) == ["almond"]
    assert foods.allergy_mentions("Plain rice", ["almond"]) == []
