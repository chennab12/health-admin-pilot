"""Small food dataset, nutrition estimates, and the grocery list.

Nutrient values are per 100 g from USDA FoodData Central (public domain).
Each row keeps its FDC ID so anyone can look the food up at
https://fdc.nal.usda.gov/ and check it. Portion sizes are typical household
measures chosen for this app, not USDA values: weigh your own food or read
the package label when it matters.

Missing data stays missing. A nutrient we do not know is None, never 0, and
every total says how many items it could not include.
"""

from __future__ import annotations

import re

NUTRIENTS = ["kcal", "protein_g", "carbs_g", "fat_g", "fiber_g"]
NUTRIENT_LABELS = {"kcal": "Calories (kcal)", "protein_g": "Protein (g)", "carbs_g": "Carbohydrates (g)",
                   "fat_g": "Fat (g)", "fiber_g": "Fiber (g)"}

# name, FDC ID, FDC description, kcal, protein, carbs, fat, fiber (per 100 g), portion label, portion grams
_ROWS = [
    ("Banana", 173944, "Bananas, raw", 89, 1.09, 22.8, 0.33, 2.6, "1 medium", 118),
    ("Apple", 2709215, "Apple, raw", 61, 0.17, 14.8, 0.15, 2.1, "1 medium", 182),
    ("Broccoli", 170379, "Broccoli, raw", 34, 2.82, 6.64, 0.37, 2.6, "1 cup chopped", 91),
    ("Spinach", 168462, "Spinach, raw", 23, 2.86, 3.63, 0.39, 2.2, "1 cup", 30),
    ("Carrot", 170393, "Carrots, raw", 41, 0.93, 9.58, 0.24, 2.8, "1 medium", 61),
    ("Sweet potato", 168482, "Sweet potato, raw, unprepared", 86, 1.57, 20.1, 0.05, 3.0, "1 medium", 130),
    ("Almonds", 170567, "Nuts, almonds", 579, 21.1, 21.6, 49.9, 12.5, "1 oz (about 23 nuts)", 28),
    ("Egg, hard-boiled", 173424, "Egg, whole, cooked, hard-boiled", 155, 12.6, 1.12, 10.6, 0.0, "1 large", 50),
    ("Lentils, cooked", 172421, "Lentils, mature seeds, cooked, boiled, without salt", 116, 9.02, 20.1, 0.38, 7.9,
     "1 cup", 198),
    ("Black beans, cooked", 173735, "Beans, black, mature seeds, cooked, boiled, without salt", 132, 8.86, 23.7,
     0.54, 8.7, "1 cup", 172),
    ("Chicken breast, roasted", 171477, "Chicken, broilers or fryers, breast, meat only, cooked, roasted", 165,
     31.0, 0.0, 3.57, 0.0, "3 oz", 85),
    ("Salmon, cooked", 175168, "Fish, salmon, Atlantic, farmed, cooked, dry heat", 206, 22.1, 0.0, 12.3, 0.0,
     "3 oz", 85),
    ("White rice, cooked", 168878, "Rice, white, long-grain, regular, enriched, cooked", 130, 2.69, 28.2, 0.28, 0.4,
     "1 cup", 158),
    ("Pasta, cooked", 2708357, "Pasta, cooked", 157, 5.76, 30.7, 0.92, 1.8, "1 cup", 140),
    ("Oats, dry", 173904, "Cereals, oats, regular and quick, not fortified, dry", 379, 13.2, 67.7, 6.52, 10.1,
     "1/2 cup dry", 40),
    ("Whole-wheat bread", 335240, "Bread, whole-wheat, commercially prepared", 254, 12.3, 43.1, 3.55, 6.0,
     "1 slice", 32),
    ("Greek yogurt", 2705415, "Yogurt, Greek, NS as to type of milk or flavor", 91, 9.11, 10.8, 1.33, 0.1,
     "1 container (6 oz)", 170),
    ("Milk", 2705384, "Milk, NFS", 52, 3.33, 4.83, 2.14, 0.0, "1 cup", 244),
    ("Olive oil", 2710186, "Olive oil", 900, 0.0, 0.0, 100.0, 0.0, "1 tablespoon", 13.5),
]

FOODS: list[dict] = [
    {"name": r[0], "fdc_id": r[1], "fdc_description": r[2], "kcal": r[3], "protein_g": r[4], "carbs_g": r[5],
     "fat_g": r[6], "fiber_g": r[7], "portion": r[8], "portion_g": r[9], "source": "USDA FoodData Central"}
    for r in _ROWS
]
FOOD_NAMES = [f["name"] for f in FOODS]


def _num(value):
    """Return a float, or None for blanks and text that is not a number."""
    if value is None or value == "":
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return None if out != out else out  # NaN check


def food_table(custom_foods: list[dict] | None = None) -> dict[str, dict]:
    """Built-in foods plus the user's own foods, keyed by lower-case name. User foods win on a name clash."""
    table = {f["name"].lower(): dict(f) for f in FOODS}
    for food in custom_foods or []:
        name = str(food.get("name") or "").strip()
        if not name:
            continue
        row = {"name": name, "source": "Your entry", "portion": food.get("portion") or "",
               "portion_g": _num(food.get("portion_g"))}
        for n in NUTRIENTS:
            row[n] = _num(food.get(n))
        table[name.lower()] = row
    return table


def item_grams(food: dict | None, grams, portions) -> float | None:
    """Grams eaten: the grams column wins; otherwise portions x portion size; otherwise unknown."""
    g = _num(grams)
    if g is not None:
        return g if g >= 0 else None
    p = _num(portions)
    if p is not None and p >= 0 and food and _num(food.get("portion_g")) is not None:
        return p * float(food["portion_g"])
    return None


def item_nutrition(food: dict | None, grams: float | None) -> dict[str, float | None]:
    """Nutrients for one item. Unknown food, unknown grams or a blank nutrient gives None, not 0."""
    out = {}
    for n in NUTRIENTS:
        per100 = _num(food.get(n)) if food else None
        out[n] = None if per100 is None or grams is None else per100 * grams / 100.0
    return out


def total_nutrition(items: list[dict[str, float | None]]) -> dict[str, dict]:
    """Sum known values and count the items that could not be included, per nutrient."""
    out = {}
    for n in NUTRIENTS:
        known = [i[n] for i in items if i.get(n) is not None]
        out[n] = {"total": sum(known) if known else None, "known": len(known), "missing": len(items) - len(known)}
    return out


def meal_log_nutrition(meal_log: list[dict], custom_foods: list[dict] | None = None) -> list[dict]:
    """One row per logged item with grams, estimated nutrients, and a status note."""
    table = food_table(custom_foods)
    rows = []
    for rec in meal_log:
        name = str(rec.get("food") or "").strip()
        food = table.get(name.lower())
        grams = item_grams(food, rec.get("grams"), rec.get("portions"))
        nutr = item_nutrition(food, grams)
        if food is None:
            status = "Food not in dataset: add it under My foods"
        elif grams is None:
            status = "Amount missing: enter grams or portions"
        elif any(v is None for v in nutr.values()):
            status = "Some nutrients unknown for this food"
        else:
            status = "OK"
        rows.append({**rec, "grams_used": grams, **nutr, "status": status})
    return rows


def recipe_per_serving(ingredients: list[dict], servings) -> dict:
    """Recipe nutrition per serving from ingredient rows with grams and per-100 g values."""
    s = _num(servings)
    if s is None or s <= 0:
        raise ValueError("Servings must be a number greater than 0.")
    items = []
    for ing in ingredients:
        grams = _num(ing.get("grams"))
        if grams is not None and grams < 0:
            raise ValueError(f"Grams cannot be negative ({ing.get('ingredient') or 'unnamed ingredient'}).")
        items.append(item_nutrition(ing, grams))
    totals = total_nutrition(items)
    return {n: {"per_serving": None if t["total"] is None else t["total"] / s, "missing": t["missing"],
                "known": t["known"]} for n, t in totals.items()}


# ---------------------------------------------------------------------------
# Grocery list from meal-plan ingredient text, e.g. "Oats 80 g; Milk 500 ml; Bananas 2"
# ---------------------------------------------------------------------------

UNIT_ALIASES = {
    "g": ("g", 1), "gram": ("g", 1), "grams": ("g", 1), "kg": ("g", 1000),
    "ml": ("ml", 1), "l": ("ml", 1000), "liter": ("ml", 1000), "litre": ("ml", 1000),
    "oz": ("oz", 1), "lb": ("lb", 1), "lbs": ("lb", 1),
    "cup": ("cup", 1), "cups": ("cup", 1), "tbsp": ("tbsp", 1), "tsp": ("tsp", 1),
    "item": ("item", 1), "items": ("item", 1), "pc": ("item", 1), "pcs": ("item", 1),
    "can": ("can", 1), "cans": ("can", 1), "bunch": ("bunch", 1), "pack": ("pack", 1), "slice": ("slice", 1),
    "slices": ("slice", 1),
}
_ING_RE = re.compile(r"^(?P<name>.*?[^\d\s].*?)\s+(?P<qty>\d+(?:\.\d+)?)\s*(?P<unit>[A-Za-z]+)?\.?$")


def parse_ingredients(text: str) -> list[dict]:
    """Split 'Name qty unit; Name qty unit' text. Unreadable parts are kept with qty None."""
    out = []
    for part in re.split(r"[;\n]+", str(text or "")):
        part = part.strip()
        if not part:
            continue
        m = _ING_RE.match(part)
        if not m:
            out.append({"item": part, "qty": None, "unit": "", "note": "No amount found"})
            continue
        unit_raw = (m.group("unit") or "item").lower()
        unit, factor = UNIT_ALIASES.get(unit_raw, (unit_raw, 1))
        out.append({"item": m.group("name").strip(), "qty": float(m.group("qty")) * factor, "unit": unit, "note": ""})
    return out


def grocery_list(meal_plan: list[dict]) -> list[dict]:
    """Combine ingredients across the week. Same item + same unit are added; different units stay separate."""
    combined: dict[tuple[str, str], dict] = {}
    for rec in meal_plan:
        for ing in parse_ingredients(rec.get("ingredients", "")):
            key = (ing["item"].lower(), ing["unit"])
            row = combined.setdefault(key, {"item": ing["item"], "quantity": 0.0, "unit": ing["unit"],
                                            "used_in": [], "note": ""})
            if ing["qty"] is None:
                row["quantity"] = None
                row["note"] = "Amount not given"
            elif row["quantity"] is not None:
                row["quantity"] += ing["qty"]
            dish = str(rec.get("dish") or "").strip()
            if dish and dish not in row["used_in"]:
                row["used_in"].append(dish)
    rows = sorted(combined.values(), key=lambda r: r["item"].lower())
    names = [r["item"].lower() for r in rows]
    for r in rows:
        r["used_in"] = ", ".join(r["used_in"])
        if names.count(r["item"].lower()) > 1 and not r["note"]:
            r["note"] = "Listed in more than one unit: not converted"
    return rows


def allergy_mentions(text: str, allergy_terms: list[str]) -> list[str]:
    """Words from the allergy list that appear in the text. A text match only: no match does NOT mean safe."""
    low = str(text or "").lower()
    return [t for t in allergy_terms if t and re.search(r"\b" + re.escape(t.lower()), low)]
