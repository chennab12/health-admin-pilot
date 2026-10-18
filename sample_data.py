"""Synthetic sample family for the demo.

Everyone and everything here is made up. Dates are relative to today so the
demo always looks current. Gaps are deliberate: some nights, weeks and meals
are not logged, so the app can show how it handles missing data.
"""

from __future__ import annotations

import random
from datetime import date, timedelta

import storage

S = storage.ORIGIN_SAMPLE


def sample_data(today: date) -> dict:
    rng = random.Random(42)
    d = lambda days: (today + timedelta(days=days)).isoformat()  # noqa: E731
    data = storage.empty_data()
    data["settings"]["is_sample"] = True

    data["profiles"] = [
        {"name": "Alex", "age_group": "Adult (20+)", "birth_year": 1984, "notes": "Synthetic sample adult"},
        {"name": "Jordan", "age_group": "Adult (20+)", "birth_year": 1987, "notes": "Synthetic sample adult"},
        {"name": "Maya", "age_group": "Teen (13–19)", "birth_year": 2012, "notes": "Synthetic sample teen"},
        {"name": "Leo", "age_group": "Child (2–12)", "birth_year": 2018, "notes": "Synthetic sample child"},
    ]

    data["habits"] = [
        {"profile": "Alex", "habit": "Water with each meal", "days_per_week": 7, "active": True},
        {"profile": "Alex", "habit": "10-minute stretch", "days_per_week": 5, "active": True},
        {"profile": "Jordan", "habit": "Lights out by 23:00", "days_per_week": 5, "active": True},
        {"profile": "Jordan", "habit": "Walk after dinner", "days_per_week": 4, "active": True},
        {"profile": "Maya", "habit": "Screens off 30 min before bed", "days_per_week": 5, "active": True},
        {"profile": "Leo", "habit": "Brush teeth twice", "days_per_week": 7, "active": True},
    ]
    log = []
    for back in range(1, 22):
        for h in data["habits"]:
            if rng.random() < 0.15:  # not logged at all that day
                continue
            log.append({"date": d(-back), "profile": h["profile"], "habit": h["habit"],
                        "done": rng.random() < h["days_per_week"] / 7.5})
    data["habit_log"] = log

    data["food_prefs"] = [
        {"profile": "Alex", "likes": "Lentil dishes, salads", "allergies": "", "restrictions": "",
         "max_prep_minutes": 30},
        {"profile": "Jordan", "likes": "Fish, rice bowls", "allergies": "almond", "restrictions": "",
         "max_prep_minutes": 25},
        {"profile": "Maya", "likes": "Pasta, smoothies", "allergies": "", "restrictions": "Vegetarian",
         "max_prep_minutes": None},
        {"profile": "Leo", "likes": "Pasta, bananas", "allergies": "", "restrictions": "", "max_prep_minutes": None},
    ]

    E = storage.EVERYONE
    data["meal_plan"] = [
        {"day": "Mon", "meal": "Breakfast", "for_whom": E, "dish": "Overnight oats",
         "prep_minutes": 10, "ingredients": "Oats 160 g; Milk 500 ml; Bananas 2"},
        {"day": "Mon", "meal": "Dinner", "for_whom": E, "dish": "Lentil curry with rice",
         "prep_minutes": 35, "ingredients": "Lentils 400 g; Rice 300 g; Spinach 100 g; Onion 1"},
        {"day": "Tue", "meal": "Lunch", "for_whom": "Alex", "dish": "Bean and veggie bowl",
         "prep_minutes": 15, "ingredients": "Black beans 1 can; Carrots 2; Rice 150 g"},
        {"day": "Tue", "meal": "Dinner", "for_whom": E, "dish": "Salmon, sweet potato and broccoli",
         "prep_minutes": 30, "ingredients": "Salmon 600 g; Sweet potatoes 4; Broccoli 1 bunch"},
        {"day": "Wed", "meal": "Breakfast", "for_whom": E, "dish": "Yogurt bowl with almonds",
         "prep_minutes": 5, "ingredients": "Greek yogurt 680 g; Almonds 60 g; Bananas 2"},
        {"day": "Wed", "meal": "Dinner", "for_whom": E, "dish": "Pasta with spinach",
         "prep_minutes": 25, "ingredients": "Pasta 450 g; Spinach 150 g; Olive oil 2 tbsp"},
        {"day": "Thu", "meal": "Dinner", "for_whom": E, "dish": "Roast chicken with carrots",
         "prep_minutes": 45, "ingredients": "Chicken breast 0.8 kg; Carrots 6; Olive oil 1 tbsp"},
        {"day": "Fri", "meal": "Lunch", "for_whom": "Maya", "dish": "Veggie wrap",
         "prep_minutes": 5, "ingredients": "Veggie wraps 2"},
        {"day": "Sat", "meal": "Breakfast", "for_whom": E, "dish": "Eggs and toast",
         "prep_minutes": 15, "ingredients": "Eggs 8; Whole-wheat bread 8 slices"},
        {"day": "Sun", "meal": "Dinner", "for_whom": E, "dish": "Black bean tacos",
         "prep_minutes": 20, "ingredients": "Black beans 2 cans; Tortillas 1 pack; Salsa"},
    ]

    data["custom_foods"] = [
        {"name": "Veggie wrap (store-bought)", "kcal": 210, "protein_g": 7, "carbs_g": 30, "fat_g": 7,
         "fiber_g": None, "portion": "1 wrap", "portion_g": 150,
         "source_note": "Sample package label: fiber not listed"},
    ]
    meal_log = []
    menu = [("Breakfast", "Oats, dry", 1, None), ("Breakfast", "Banana", 1, None), ("Lunch", "Lentils, cooked", 1, None),
            ("Lunch", "White rice, cooked", 1, None), ("Dinner", "Salmon, cooked", None, 120),
            ("Dinner", "Broccoli", 1, None), ("Snack", "Apple", 1, None), ("Snack", "Greek yogurt", 1, None),
            ("Dinner", "Chicken breast, roasted", 1, None), ("Lunch", "Veggie wrap (store-bought)", 1, None)]
    for back in range(0, 12):
        for person in ("Alex", "Maya"):
            if back in (4, 5) and person == "Alex":
                continue  # not logged: unknown, not zero
            for meal, food, portions, grams in rng.sample(menu, 4):
                if person == "Maya" and food in ("Salmon, cooked", "Chicken breast, roasted"):
                    food, portions, grams = "Black beans, cooked", 1, None
                meal_log.append({"date": d(-back), "profile": person, "meal": meal, "food": food,
                                 "portions": portions, "grams": grams, "notes": ""})
    meal_log.append({"date": d(-1), "profile": "Alex", "meal": "Snack", "food": "Trail mix", "portions": None,
                     "grams": None, "notes": "Not in the food list yet"})
    data["meal_log"] = meal_log
    data["nutrition_goals"] = [
        {"profile": "Alex", "kcal": None, "protein_g": 90, "fiber_g": 30, "notes": "Own goal: more fiber"},
        {"profile": "Maya", "kcal": None, "protein_g": None, "fiber_g": 25, "notes": "Own goal"},
    ]

    activity = []
    for back in range(0, 42):
        day = today - timedelta(days=back)
        if 15 <= back <= 19:
            continue  # a week away: nothing logged
        if rng.random() < 0.8:
            activity.append({"date": day.isoformat(), "profile": "Alex", "activity_type": "Walking",
                             "minutes": rng.choice([20, 25, 30, 35, 40]), "steps": rng.randint(5200, 10400),
                             "notes": ""})
        if day.weekday() in (0, 3):
            activity.append({"date": day.isoformat(), "profile": "Alex", "activity_type": "Strength",
                             "minutes": 20, "steps": None, "notes": "Bodyweight circuit"})
        if day.weekday() in (1, 3, 5) and rng.random() < 0.85:
            activity.append({"date": day.isoformat(), "profile": "Jordan", "activity_type": "Mobility",
                             "minutes": rng.choice([10, 12, 15]), "steps": None, "notes": "Stretching video"})
        if day.weekday() in (2, 5) and back < 28:
            activity.append({"date": day.isoformat(), "profile": "Maya", "activity_type": "Activity",
                             "minutes": 60, "steps": None, "notes": "Soccer practice"})
    data["activity_log"] = activity
    data["activity_goals"] = [
        {"profile": "Alex", "weekly_minutes": 150, "strength_sessions": 2, "mobility_sessions": 1,
         "daily_steps": 7000},
        {"profile": "Jordan", "weekly_minutes": 90, "strength_sessions": 0, "mobility_sessions": 3,
         "daily_steps": None},
    ]
    data["activity_templates"] = [
        {"profile": "Alex", "name": "Brisk walk", "activity_type": "Walking", "days": "Mon, Tue, Thu, Sat", "start_date": d(-14),
         "minutes": 25, "weekly_step": 5, "cap_minutes": 40, "notes": "Add 5 min a week, stop at 40"},
        {"profile": "Alex", "name": "Bodyweight strength", "activity_type": "Strength", "days": "Mon, Thu", "start_date": d(-14),
         "minutes": 20, "weekly_step": 0, "cap_minutes": 20, "notes": "Squats, wall push-ups, rows"},
        {"profile": "Jordan", "name": "Gentle stretching", "activity_type": "Mobility", "days": "Tue, Thu, Sat", "start_date": d(-21),
         "minutes": 10, "weekly_step": 2, "cap_minutes": 20, "notes": ""},
        {"profile": "Maya", "name": "Soccer practice", "activity_type": "Activity", "days": "Wed, Sat", "start_date": d(-28),
         "minutes": 60, "weekly_step": 0, "cap_minutes": 60, "notes": "Team schedule"},
    ]

    data["sleep_plan"] = [
        {"profile": "Alex", "target_bedtime": "23:00", "target_wake": "06:45"},
        {"profile": "Jordan", "target_bedtime": "23:30", "target_wake": "07:15"},
        {"profile": "Maya", "target_bedtime": "22:00", "target_wake": "06:45"},
        {"profile": "Leo", "target_bedtime": "20:30", "target_wake": "06:45"},
    ]
    sleep = []
    for back in range(1, 29):
        night = today - timedelta(days=back)
        for person, base_bed, base_wake, nights in (("Alex", 23.0, 6.75, 28), ("Jordan", 23.6, 7.2, 21),
                                                    ("Maya", 22.2, 6.75, 14)):
            if back > nights or rng.random() < 0.15:
                continue  # night not logged
            late = 1.2 if (person == "Alex" and back <= 7) else 0.0  # Alex went to bed later this week
            bed = (base_bed + late + rng.uniform(-0.4, 0.6)) % 24
            wake = base_wake + rng.uniform(-0.3, 0.3)
            in_bed = (wake - bed) % 24
            est = round(in_bed - rng.uniform(0.2, 0.6), 1) if rng.random() < 0.7 else None
            sleep.append({"date": night.isoformat(), "profile": person,
                          "bedtime": _clock(bed), "wake_time": _clock(wake), "est_sleep_hours": est,
                          "energy": rng.randint(2, 5), "mood": rng.randint(2, 5), "stress": rng.randint(1, 4),
                          "notes": "Late work call" if (person == "Alex" and back == 3) else ""})
    data["sleep_log"] = sleep

    meas = []
    for week in range(0, 16):
        if 6 <= week <= 9:
            continue  # four weeks with no weigh-ins: shown as a gap
        meas.append({"date": d(-7 * week - 1), "profile": "Alex", "measure": "Weight",
                     "value": round(184.0 + week * 0.25 + rng.uniform(-0.8, 0.8), 1), "value2": None, "unit": "lb",
                     "notes": ""})
        if week % 2 == 0:
            meas.append({"date": d(-7 * week - 2), "profile": "Jordan", "measure": "Weight",
                         "value": round(63.5 + rng.uniform(-0.6, 0.6), 1), "value2": None, "unit": "kg",
                         "notes": ""})
    for back in (2, 5, 9, 12, 16, 19, 23, 26, 30):
        meas.append({"date": d(-back), "profile": "Alex", "measure": "Blood pressure",
                     "value": rng.randint(118, 134), "value2": rng.randint(74, 86), "unit": "mmHg",
                     "notes": "Home cuff, seated, morning"})
    meas += [
        {"date": d(-40), "profile": "Alex", "measure": "Height", "value": 70, "value2": None, "unit": "in",
         "notes": "At clinic"},
        {"date": d(-40), "profile": "Alex", "measure": "Waist", "value": 36, "value2": None, "unit": "in",
         "notes": ""},
        {"date": d(-60), "profile": "Leo", "measure": "Height", "value": 128, "value2": None, "unit": "cm",
         "notes": "Well-child visit"},
        {"date": d(-60), "profile": "Leo", "measure": "Weight", "value": 26.4, "value2": None, "unit": "kg",
         "notes": "Well-child visit"},
        {"date": d(-90), "profile": "Maya", "measure": "Height", "value": 158, "value2": None, "unit": "cm",
         "notes": ""},
    ]
    data["measurements"] = sorted(meas, key=lambda r: r["date"])

    data["visits"] = [
        {"date": d(-40), "profile": "Alex", "clinician": "Dr. Rivera (primary care, sample)",
         "reason": "Annual check-up", "summary": "Routine visit. Asked to track blood pressure at home.",
         "follow_up": "Return in about 6 weeks with home readings"},
        {"date": d(-60), "profile": "Leo", "clinician": "Pediatric clinic (sample)", "reason": "Well-child visit",
         "summary": "Growth measured. Flu vaccine given.", "follow_up": "Schedule eye exam"},
    ]
    data["vaccinations"] = [
        {"date": d(-60), "profile": "Leo", "vaccine": "Influenza (seasonal)", "dose_note": "This season",
         "given_at": "Pediatric clinic (sample)", "next_due": None},
        {"date": d(-150), "profile": "Maya", "vaccine": "HPV", "dose_note": "Dose 1",
         "given_at": "Pediatric clinic (sample)", "next_due": d(20)},
        {"date": d(-400), "profile": "Alex", "vaccine": "Tdap", "dose_note": "", "given_at": "Pharmacy (sample)",
         "next_due": None},
    ]
    data["instructions"] = [
        {"date": d(-40), "profile": "Alex", "clinician": "Dr. Rivera (sample)",
         "instruction": "Check blood pressure at home twice a week, seated, and bring the log to the next visit.",
         "until": d(2)},
        {"date": d(-200), "profile": "Maya", "clinician": "Dr. Okafor (sample)",
         "instruction": "Follow the written asthma action plan from the clinic. Keep the inhaler in the sports bag.",
         "until": None},
    ]
    data["medications"] = [
        {"profile": "Jordan", "medication": "Levothyroxine (sample)",
         "prescribed_schedule": "As printed on the pharmacy label: once each morning", "prescriber": "Dr. Chen",
         "schedule_confirmed": True, "refill_date": d(5), "active": True, "notes": ""},
        {"profile": "Maya", "medication": "Albuterol inhaler (sample)",
         "prescribed_schedule": "As written in the asthma action plan", "prescriber": "Dr. Okafor",
         "schedule_confirmed": True, "refill_date": d(40), "active": True, "notes": "Check expiry date"},
        {"profile": "Alex", "medication": "Vitamin D (sample)", "prescribed_schedule": "",
         "prescriber": "", "schedule_confirmed": False, "refill_date": None, "active": True,
         "notes": "Ask at next visit whether to continue"},
    ]
    data["appointments"] = [
        {"date": d(2), "time": "10:30", "profile": "Alex", "with_whom": "Dr. Rivera (primary care, sample)",
         "purpose": "Blood pressure follow-up", "location": "Main St clinic", "prep_done": False},
        {"date": d(9), "time": "15:45", "profile": "Leo", "with_whom": "Family dentist (sample)",
         "purpose": "Cleaning", "location": "", "prep_done": False},
        {"date": d(20), "time": "09:00", "profile": "Maya", "with_whom": "Pediatric clinic (sample)",
         "purpose": "HPV dose 2", "location": "", "prep_done": False},
    ]
    data["care_tasks"] = [
        {"due_date": d(2), "profile": "Alex", "task": "Bring home blood pressure log to appointment",
         "confirmed": True, "done": False, "notes": "From clinician instruction"},
        {"due_date": d(5), "profile": "Jordan", "task": "Pick up prescription refill", "confirmed": True,
         "done": False, "notes": ""},
        {"due_date": d(-3), "profile": "Leo", "task": "Schedule eye exam", "confirmed": True, "done": False,
         "notes": "Follow-up from well-child visit"},
        {"due_date": d(6), "profile": "Maya", "task": "Return school sports form", "confirmed": False,
         "done": False, "notes": "Check whether the school still needs it"},
    ]
    data["questions"] = [
        {"profile": "Alex", "for_appointment": "Blood pressure follow-up",
         "question": "Am I taking home readings the right way?", "asked": False},
        {"profile": "Alex", "for_appointment": "Blood pressure follow-up",
         "question": "Should I keep taking vitamin D?", "asked": False},
    ]

    for key in storage.LIST_KEYS:
        data[key] = storage.clean_records(key, data[key], default_origin=S)
    return data


def _clock(hours: float) -> str:
    hours %= 24
    h = int(hours)
    m = int(round((hours - h) * 60))
    if m == 60:
        h, m = (h + 1) % 24, 0
    return f"{h:02d}:{m:02d}"
