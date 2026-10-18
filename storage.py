"""Record tables, validation, filters, and JSON backup/restore.

Nothing is saved on a server. Records live in the visitor's Streamlit session
and disappear when the session resets, unless the visitor downloads a JSON
backup and uploads it again later.

Every record list is a list of plain dicts. SCHEMAS says which fields each
list has and their type. Every record also has an "origin" field: "Sample"
for the synthetic demo records and "You" for anything a person enters.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time

import pandas as pd

import calculations as calc

APP_ID = "family-health-wellness-copilot"
SCHEMA_VERSION = 1
MAX_BACKUP_BYTES = 5 * 1024 * 1024
MAX_ROWS_PER_TABLE = 5000

ORIGIN_SAMPLE, ORIGIN_USER = "Sample", "You"
EVERYONE = "Everyone"

AGE_GROUPS = ["Adult (20+)", "Teen (13–19)", "Child (2–12)", "Under 2"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
MEALS = ["Breakfast", "Lunch", "Dinner", "Snack"]
ACTIVITY_TYPES = ["Walking", "Activity", "Strength", "Mobility", "Other"]
MEASURES = {  # measure -> allowed units
    "Weight": ["kg", "lb"],
    "Height": ["cm", "in"],
    "Waist": ["cm", "in"],
    "Blood pressure": ["mmHg"],
    "Resting heart rate": ["bpm"],
    "Other": [],
}
UNITS = sorted({u for units in MEASURES.values() for u in units})

# Field -> type. Types: str, float, int, date, time, bool.
SCHEMAS: dict[str, dict[str, str]] = {
    "profiles": {"name": "str", "age_group": "str", "birth_year": "int", "notes": "str"},
    "habits": {"profile": "str", "habit": "str", "days_per_week": "int", "active": "bool"},
    "habit_log": {"date": "date", "profile": "str", "habit": "str", "done": "bool"},
    "food_prefs": {"profile": "str", "likes": "str", "allergies": "str", "restrictions": "str",
                   "max_prep_minutes": "int"},
    "meal_plan": {"day": "str", "meal": "str", "for_whom": "str", "dish": "str", "prep_minutes": "int",
                  "ingredients": "str"},
    "meal_log": {"date": "date", "profile": "str", "meal": "str", "food": "str", "portions": "float",
                 "grams": "float", "notes": "str"},
    "custom_foods": {"name": "str", "kcal": "float", "protein_g": "float", "carbs_g": "float", "fat_g": "float",
                     "fiber_g": "float", "portion": "str", "portion_g": "float", "source_note": "str"},
    "nutrition_goals": {"profile": "str", "kcal": "float", "protein_g": "float", "fiber_g": "float",
                        "notes": "str"},
    "activity_log": {"date": "date", "profile": "str", "activity_type": "str", "minutes": "float",
                     "steps": "int", "notes": "str"},
    "activity_goals": {"profile": "str", "weekly_minutes": "float", "strength_sessions": "int",
                       "mobility_sessions": "int", "daily_steps": "int"},
    "activity_templates": {"profile": "str", "name": "str", "activity_type": "str", "days": "str",
                           "start_date": "date", "minutes": "float", "weekly_step": "float", "cap_minutes": "float",
                           "notes": "str"},
    "sleep_plan": {"profile": "str", "target_bedtime": "time", "target_wake": "time"},
    "sleep_log": {"date": "date", "profile": "str", "bedtime": "time", "wake_time": "time",
                  "est_sleep_hours": "float", "energy": "int", "mood": "int", "stress": "int", "notes": "str"},
    "measurements": {"date": "date", "profile": "str", "measure": "str", "value": "float", "value2": "float",
                     "unit": "str", "notes": "str"},
    "visits": {"date": "date", "profile": "str", "clinician": "str", "reason": "str", "summary": "str",
               "follow_up": "str"},
    "vaccinations": {"date": "date", "profile": "str", "vaccine": "str", "dose_note": "str", "given_at": "str",
                     "next_due": "date"},
    "instructions": {"date": "date", "profile": "str", "clinician": "str", "instruction": "str", "until": "date"},
    "medications": {"profile": "str", "medication": "str", "prescribed_schedule": "str", "prescriber": "str",
                    "schedule_confirmed": "bool", "refill_date": "date", "active": "bool", "notes": "str"},
    "appointments": {"date": "date", "time": "time", "profile": "str", "with_whom": "str", "purpose": "str",
                     "location": "str", "prep_done": "bool"},
    "care_tasks": {"due_date": "date", "profile": "str", "task": "str", "confirmed": "bool", "done": "bool",
                   "notes": "str"},
    "questions": {"profile": "str", "for_appointment": "str", "question": "str", "asked": "bool"},
}
LIST_KEYS = list(SCHEMAS)
# Logs describe the past: a date after today is flagged.
PAST_ONLY = {"habit_log", "meal_log", "activity_log", "sleep_log", "measurements", "visits", "vaccinations"}
BOOL_DEFAULT_TRUE = {"active"}
DEFAULT_SETTINGS = {"units": "US (lb, in)", "is_sample": False}


def empty_data() -> dict:
    data = {key: [] for key in LIST_KEYS}
    data["settings"] = dict(DEFAULT_SETTINGS)
    return data


# ---------------------------------------------------------------------------
# Coercion: turn editor output or JSON values into clean, typed values
# ---------------------------------------------------------------------------

def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    if isinstance(value, str) and value.strip().lower() in ("", "nan", "nat", "none"):
        return True
    if isinstance(value, (list, dict)):
        return False
    try:  # pandas NaT / NA
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def coerce(value, kind: str):
    if _is_blank(value):
        return None
    if kind == "float":
        try:
            out = float(value)
        except (TypeError, ValueError):
            return None
        return round(out, 3) if out == out else None
    if kind == "int":
        try:
            return int(round(float(value)))
        except (TypeError, ValueError):
            return None
    if kind == "bool":
        if isinstance(value, str):
            return value.strip().lower() in ("true", "1", "yes", "y")
        return bool(value)
    if kind == "date":
        if isinstance(value, datetime):
            return value.date().isoformat()
        if isinstance(value, date):
            return value.isoformat()
        if hasattr(value, "date") and callable(value.date):  # pandas Timestamp
            return value.date().isoformat()
        try:
            return date.fromisoformat(str(value)[:10]).isoformat()
        except ValueError:
            return None
    if kind == "time":
        try:
            t = calc.parse_clock(value)
        except ValueError:
            return None
        return t.strftime("%H:%M") if t else None
    return str(value).strip()[:500]


def clean_records(key: str, records, default_origin: str = ORIGIN_USER) -> list[dict]:
    """Keep only known fields with the right types; drop rows that are entirely empty."""
    schema = SCHEMAS[key]
    out = []
    if not isinstance(records, list):
        return out
    for rec in records[:MAX_ROWS_PER_TABLE]:
        if not isinstance(rec, dict):
            continue
        row = {f: coerce(rec.get(f), kind) for f, kind in schema.items()}
        if all(v in (None, "", False) for v in row.values()):
            continue
        for f, kind in schema.items():
            if kind == "bool" and row[f] is None:
                row[f] = f in BOOL_DEFAULT_TRUE
        origin = rec.get("origin")
        row["origin"] = origin if origin in (ORIGIN_SAMPLE, ORIGIN_USER) else default_origin
        out.append(row)
    return out


# ---------------------------------------------------------------------------
# Validation: plain-language problems for each row
# ---------------------------------------------------------------------------

def _range(issues, label, value, low, high, unit=""):
    if value is not None and not low <= value <= high:
        issues.append(f"{label} {value:g}{unit} is outside {low:g}–{high:g}{unit}.")


MEASURE_LIMITS = {  # (measure, unit) -> (low, high)
    ("Weight", "kg"): (0.5, 400), ("Weight", "lb"): (1, 880),
    ("Height", "cm"): (30, 260), ("Height", "in"): (12, 102),
    ("Waist", "cm"): (20, 250), ("Waist", "in"): (8, 100),
    ("Resting heart rate", "bpm"): (20, 250),
}


def row_issues(key: str, rec: dict, today: date, profile_names: set[str] | None = None) -> list[str]:
    issues: list[str] = []
    schema = SCHEMAS[key]
    if "date" in schema:
        if rec.get("date") is None:
            issues.append("Date is missing or not a real date (use YYYY-MM-DD).")
        elif key in PAST_ONLY and rec["date"] > today.isoformat():
            issues.append("Date is in the future; logs describe things that already happened.")
    if profile_names is not None and "profile" in schema:
        if not rec.get("profile"):
            issues.append("Choose a family member.")
        elif rec["profile"] not in profile_names:
            issues.append(f"'{rec['profile']}' is not a family profile.")
    if key == "meal_plan" and rec.get("for_whom") and profile_names is not None:
        if rec["for_whom"] != EVERYONE and rec["for_whom"] not in profile_names:
            issues.append(f"'{rec['for_whom']}' is not a family profile.")
    if key == "meal_plan":
        if rec.get("day") not in DAYS:
            issues.append("Day must be Mon–Sun.")
        _range(issues, "Prep time", rec.get("prep_minutes"), 0, 600, " min")
    if key == "profiles":
        if not rec.get("name"):
            issues.append("Name is required (a first name or nickname is enough).")
        if rec.get("age_group") not in AGE_GROUPS:
            issues.append("Choose an age group.")
        _range(issues, "Birth year", rec.get("birth_year"), 1900, today.year)
    if key == "habits":
        _range(issues, "Days per week", rec.get("days_per_week"), 1, 7)
    if key == "meal_log":
        _range(issues, "Portions", rec.get("portions"), 0, 50)
        _range(issues, "Grams", rec.get("grams"), 0, 5000, " g")
        if not rec.get("food"):
            issues.append("Food name is missing.")
    if key == "custom_foods":
        for n in ("protein_g", "carbs_g", "fat_g", "fiber_g"):
            _range(issues, n.replace("_g", "").capitalize() + " per 100 g", rec.get(n), 0, 100, " g")
        _range(issues, "Calories per 100 g", rec.get("kcal"), 0, 900)
        _range(issues, "Portion", rec.get("portion_g"), 0, 5000, " g")
    if key == "nutrition_goals":
        _range(issues, "Calories goal", rec.get("kcal"), 0, 10000)
        _range(issues, "Protein goal", rec.get("protein_g"), 0, 500, " g")
        _range(issues, "Fiber goal", rec.get("fiber_g"), 0, 200, " g")
    if key == "activity_log":
        _range(issues, "Minutes", rec.get("minutes"), 0, 1440)
        _range(issues, "Steps", rec.get("steps"), 0, 100000)
        if rec.get("activity_type") not in ACTIVITY_TYPES:
            issues.append("Choose an activity type.")
    if key == "activity_goals":
        _range(issues, "Weekly minutes", rec.get("weekly_minutes"), 0, 10080)
        _range(issues, "Daily steps", rec.get("daily_steps"), 0, 100000)
        _range(issues, "Strength sessions", rec.get("strength_sessions"), 0, 14)
        _range(issues, "Mobility sessions", rec.get("mobility_sessions"), 0, 14)
    if key == "activity_templates":
        _range(issues, "Minutes", rec.get("minutes"), 1, 600)
        _range(issues, "Weekly step", rec.get("weekly_step"), 0, 60)
        if rec.get("cap_minutes") is not None and rec.get("minutes") is not None and rec["cap_minutes"] < rec["minutes"]:
            issues.append("Cap is lower than the starting minutes.")
        bad = [d for d in parse_days(rec.get("days")) if d not in DAYS]
        if bad:
            issues.append("Days must be like 'Mon, Wed, Fri'.")
    if key == "sleep_log":
        if rec.get("bedtime") is None or rec.get("wake_time") is None:
            if rec.get("est_sleep_hours") is None:
                issues.append("Enter bedtime and wake time, or an estimated sleep length.")
        _range(issues, "Estimated sleep", rec.get("est_sleep_hours"), 0, 24, " h")
        for f in ("energy", "mood", "stress"):
            _range(issues, f.capitalize(), rec.get(f), 1, 5)
        if rec.get("bedtime") and rec.get("wake_time") and rec.get("est_sleep_hours") is not None:
            in_bed = calc.sleep_hours(rec["bedtime"], rec["wake_time"])
            if rec["est_sleep_hours"] > in_bed + 0.01:
                issues.append(f"Estimated sleep ({rec['est_sleep_hours']:g} h) is longer than time in bed "
                              f"({in_bed:.1f} h).")
    if key == "measurements":
        measure, unit = rec.get("measure"), rec.get("unit")
        v, v2 = rec.get("value"), rec.get("value2")
        if measure not in MEASURES:
            issues.append("Choose what was measured.")
        elif MEASURES[measure] and unit not in MEASURES[measure]:
            issues.append(f"{measure} must use {' or '.join(MEASURES[measure])}.")
        if v is None:
            issues.append("Value is missing.")
        elif measure == "Blood pressure":
            _range(issues, "Systolic (top number)", v, 50, 300)
            if v2 is None:
                issues.append("Blood pressure needs the bottom number (diastolic) in 'Value 2'.")
            else:
                _range(issues, "Diastolic (bottom number)", v2, 20, 200)
                if v2 >= v:
                    issues.append("The top number (systolic) should be higher than the bottom number.")
        elif (measure, unit) in MEASURE_LIMITS:
            low, high = MEASURE_LIMITS[(measure, unit)]
            _range(issues, measure, v, low, high, f" {unit}")
    if key == "vaccinations" and rec.get("next_due") and rec.get("date") and rec["next_due"] < rec["date"]:
        issues.append("Next due date is before the date given.")
    if key == "medications" and not rec.get("medication"):
        issues.append("Medication name is missing.")
    return issues


def table_issues(key: str, records: list[dict], today: date, profile_names: set[str] | None = None) -> list[str]:
    """'Row 3: problem' messages for the editor, numbered as the person sees them."""
    out = []
    for i, rec in enumerate(records, start=1):
        for msg in row_issues(key, rec, today, profile_names):
            out.append(f"Row {i}: {msg}")
    return out


def valid_records(key: str, records: list[dict], today: date) -> list[dict]:
    """Rows without problems. Charts and totals use these so a typo never turns into a data point."""
    return [r for r in records if not row_issues(key, r, today)]


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def parse_days(text) -> list[str]:
    return [d.strip()[:3].capitalize() for d in str(text or "").replace(";", ",").split(",") if d.strip()]


def for_profiles(records: list[dict], names, field: str = "profile") -> list[dict]:
    """Rows that belong to the chosen family members. None or 'Everyone' means no filter."""
    if names is None or names == EVERYONE:
        return list(records)
    wanted = {names} if isinstance(names, str) else set(names)
    return [r for r in records if r.get(field) in wanted]


def in_date_range(records: list[dict], start: date | None, end: date | None, field: str = "date") -> list[dict]:
    """Rows with a date between start and end (inclusive). Rows without a date are left out."""
    out = []
    for r in records:
        d = r.get(field)
        if not d:
            continue
        if start and d < start.isoformat():
            continue
        if end and d > end.isoformat():
            continue
        out.append(r)
    return out


def rename_profile(data: dict, old: str, new: str) -> int:
    """Move every record from one profile name to another. Returns the number of rows changed."""
    changed = 0
    for key, schema in SCHEMAS.items():
        fields = ["name"] if key == "profiles" else [f for f in ("profile", "for_whom") if f in schema]
        for rec in data.get(key, []):
            for field in fields:
                if rec.get(field) == old:
                    rec[field] = new
                    changed += 1
    return changed


# ---------------------------------------------------------------------------
# Backup / restore
# ---------------------------------------------------------------------------

def to_backup_json(data: dict) -> str:
    payload = {
        "app": APP_ID,
        "schema_version": SCHEMA_VERSION,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "warning": "Contains personal health information. Store it somewhere private.",
        "settings": {k: data.get("settings", {}).get(k, v) for k, v in DEFAULT_SETTINGS.items()},
    }
    for key in LIST_KEYS:
        payload[key] = clean_records(key, data.get(key, []))
    return json.dumps(payload, indent=2, ensure_ascii=False)


def from_backup_bytes(raw: bytes) -> tuple[dict, list[str]]:
    """Parse and validate an uploaded backup. Raises ValueError for unusable files."""
    if len(raw) > MAX_BACKUP_BYTES:
        raise ValueError("Backup file is larger than 5 MB.")
    try:
        payload = json.loads(raw.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"This is not a readable JSON file ({exc.__class__.__name__}).") from exc
    if not isinstance(payload, dict) or payload.get("app") != APP_ID:
        raise ValueError("This JSON file was not exported by Family Health & Wellness Copilot.")
    notes: list[str] = []
    if payload.get("schema_version") != SCHEMA_VERSION:
        notes.append("The backup came from a different app version; unknown fields were ignored.")
    data = empty_data()
    for key in LIST_KEYS:
        rows = payload.get(key)
        if rows is None:
            continue
        if not isinstance(rows, list):
            notes.append(f"'{key}' was not a list and was skipped.")
            continue
        data[key] = clean_records(key, rows)
        skipped = len([r for r in rows if isinstance(r, dict)]) - len(data[key])
        if skipped > 0:
            notes.append(f"{skipped} empty or unreadable row(s) in '{key}' were skipped.")
    settings = payload.get("settings") if isinstance(payload.get("settings"), dict) else {}
    units = settings.get("units")
    data["settings"] = {
        "units": units if units in ("US (lb, in)", "Metric (kg, cm)") else DEFAULT_SETTINGS["units"],
        "is_sample": bool(settings.get("is_sample")),
    }
    return data, notes


def has_sample_rows(data: dict) -> bool:
    return any(r.get("origin") == ORIGIN_SAMPLE for key in LIST_KEYS for r in data.get(key, []))


def remove_sample_rows(data: dict) -> int:
    removed = 0
    for key in LIST_KEYS:
        before = len(data.get(key, []))
        data[key] = [r for r in data.get(key, []) if r.get("origin") != ORIGIN_SAMPLE]
        removed += before - len(data[key])
    return removed


def time_value(text: str | None) -> time | None:
    return calc.parse_clock(text) if text else None
