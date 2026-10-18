"""Reference sources used by the app.

Every reference range or guideline shown in the app comes from one of these
pages. Each was opened and checked on the date in VERIFIED_ON. If you add a new
interpretation, add its source here first; if you cannot verify a source, leave
the interpretation out.
"""

VERIFIED_ON = "2026-10-18"

CDC_ADULT_BMI = {
    "title": "CDC: Adult BMI Categories",
    "url": "https://www.cdc.gov/bmi/adult-calculator/bmi-categories.html",
    "note": "Categories apply to adults 20 and older. BMI is a screening measure, not a diagnosis.",
}
CDC_CHILD_BMI = {
    "title": "CDC: Child and Teen BMI Calculator (ages 2 through 19)",
    "url": "https://www.cdc.gov/bmi/child-teen-calculator/",
    "note": "Children and teens use BMI-for-age percentiles, not adult categories.",
}
CDC_SLEEP = {
    "title": "CDC: About Sleep (recommended hours by age group)",
    "url": "https://www.cdc.gov/sleep/about/index.html",
    "note": "CDC table based on AASM and National Sleep Foundation consensus statements.",
}
CDC_ACTIVITY_ADULTS = {
    "title": "CDC: Adult Activity, An Overview",
    "url": "https://www.cdc.gov/physical-activity-basics/guidelines/adults.html",
    "note": "From the Physical Activity Guidelines for Americans (HHS).",
}
USDA_FDC = {
    "title": "USDA FoodData Central",
    "url": "https://fdc.nal.usda.gov/",
    "note": ("U.S. Department of Agriculture, Agricultural Research Service, Beltsville Human Nutrition "
             "Research Center. FoodData Central. Public domain (CC0 1.0)."),
}

# CDC adult BMI categories (adults 20+). Lower bound inclusive, upper exclusive.
ADULT_BMI_CATEGORIES = [
    (0.0, 18.5, "Underweight range"),
    (18.5, 25.0, "Healthy weight range"),
    (25.0, 30.0, "Overweight range"),
    (30.0, float("inf"), "Obesity range"),
]

# CDC recommended sleep per day by age group (hours). None = no upper bound given.
SLEEP_BY_AGE = [
    ("Newborn", "0–3 months", 14, 17),
    ("Infant", "4–12 months (including naps)", 12, 16),
    ("Toddler", "1–2 years (including naps)", 11, 14),
    ("Preschool", "3–5 years (including naps)", 10, 13),
    ("School age", "6–12 years", 9, 12),
    ("Teen", "13–17 years", 8, 10),
    ("Adult", "18–60 years", 7, None),
    ("Adult", "61–64 years", 7, 9),
    ("Adult", "65 years and older", 7, 8),
]

# CDC weekly activity guideline for adults.
ADULT_WEEKLY_MODERATE_MINUTES = 150
ADULT_WEEKLY_STRENGTH_DAYS = 2

ALL = [CDC_ADULT_BMI, CDC_CHILD_BMI, CDC_SLEEP, CDC_ACTIVITY_ADULTS, USDA_FDC]
