"""Calculator formulas and unit conversions.

Every function raises ValueError with a plain-language message for inputs
that are impossible or outside the range a calculator can handle, so the
app can show the message instead of a wrong number.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import sources

LB_PER_KG = 2.20462262185
CM_PER_IN = 2.54


# ---------------------------------------------------------------------------
# Unit conversions
# ---------------------------------------------------------------------------

def lb_to_kg(lb: float) -> float:
    return lb / LB_PER_KG


def kg_to_lb(kg: float) -> float:
    return kg * LB_PER_KG


def in_to_cm(inches: float) -> float:
    return inches * CM_PER_IN


def cm_to_in(cm: float) -> float:
    return cm / CM_PER_IN


def ft_in_to_cm(feet: float, inches: float) -> float:
    return in_to_cm(feet * 12 + inches)


def to_kg(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit == "kg":
        return value
    if unit in ("lb", "lbs"):
        return lb_to_kg(value)
    raise ValueError(f"Unknown weight unit '{unit}'. Use kg or lb.")


def to_cm(value: float, unit: str) -> float:
    unit = unit.lower()
    if unit == "cm":
        return value
    if unit == "in":
        return in_to_cm(value)
    raise ValueError(f"Unknown length unit '{unit}'. Use cm or in.")


# ---------------------------------------------------------------------------
# BMI and waist-to-height ratio
# ---------------------------------------------------------------------------

def bmi(weight_kg: float, height_cm: float) -> float:
    """BMI = weight (kg) / height (m) squared."""
    if not 20 <= height_cm <= 260:
        raise ValueError("Height must be between 20 and 260 cm (about 8 to 102 inches).")
    if not 1 <= weight_kg <= 400:
        raise ValueError("Weight must be between 1 and 400 kg (about 2 to 880 lb).")
    meters = height_cm / 100
    return weight_kg / (meters * meters)


def bmi_imperial(weight_lb: float, height_in: float) -> float:
    return bmi(lb_to_kg(weight_lb), in_to_cm(height_in))


def adult_bmi_category(value: float, age_years: float | None, pregnant: bool) -> tuple[str | None, str]:
    """CDC adult category, only for adults 20+ who are not pregnant. Returns (category or None, explanation)."""
    if age_years is None:
        return None, "Enter an age to see whether the adult categories apply."
    if pregnant:
        return None, ("Adult BMI categories are not used during pregnancy. Weight during pregnancy is best "
                      "discussed with the clinician who looks after the pregnancy.")
    if age_years < 2:
        return None, "BMI categories are not used for children under 2."
    if age_years < 20:
        return None, ("Adult categories do not apply under age 20. Children and teens (2 through 19) use "
                      "BMI-for-age percentiles: see the CDC Child and Teen BMI Calculator.")
    for low, high, label in sources.ADULT_BMI_CATEGORIES:
        if low <= value < high:
            return label, f"CDC adult category for a BMI of {value:.1f}: {label.lower()}."
    return None, "Could not place this value in a category."


def waist_to_height(waist: float, height: float) -> float:
    """Waist divided by height, both in the same unit. A ratio only: no interpretation is given."""
    if waist <= 0 or height <= 0:
        raise ValueError("Waist and height must both be greater than 0.")
    ratio = waist / height
    if ratio >= 1.5 or ratio <= 0.2:
        raise ValueError("Waist and height look mismatched. Check that both use the same unit (cm or in).")
    return ratio


# ---------------------------------------------------------------------------
# Sleep
# ---------------------------------------------------------------------------

def parse_clock(value) -> time | None:
    """Accept '23:15', '7:05', '11:30 pm', a datetime.time, or blank (None)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.time().replace(second=0, microsecond=0)
    if isinstance(value, time):
        return value.replace(second=0, microsecond=0)
    text = str(value).strip().lower().replace(".", "")
    if not text or text in ("nan", "nat", "none"):
        return None
    for fmt in ("%H:%M", "%H:%M:%S", "%I:%M %p", "%I:%M%p", "%I %p", "%I%p"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"'{value}' is not a clock time. Use 24-hour HH:MM such as 22:45, or 10:45 pm.")


def sleep_hours(bedtime, wake_time) -> float:
    """Hours from bedtime to wake time. A wake time at or before bedtime means the next day (crosses midnight)."""
    bed, wake = parse_clock(bedtime), parse_clock(wake_time)
    if bed is None or wake is None:
        raise ValueError("Enter both a bedtime and a wake time.")
    start = datetime.combine(date(2000, 1, 1), bed)
    end = datetime.combine(date(2000, 1, 1), wake)
    if end <= start:
        end += timedelta(days=1)
    return (end - start).total_seconds() / 3600


def clock_label(hours_after_midnight: float) -> str:
    h = int(hours_after_midnight) % 24
    m = int(round((hours_after_midnight - int(hours_after_midnight)) * 60))
    if m == 60:
        h, m = (h + 1) % 24, 0
    return f"{h:02d}:{m:02d}"


def bedtime_axis_hours(value) -> float | None:
    """Hours on an evening-centred axis: 18:00 -> 18, 23:30 -> 23.5, 01:00 -> 25. For plotting bedtimes."""
    t = parse_clock(value)
    if t is None:
        return None
    h = t.hour + t.minute / 60
    return h + 24 if h < 15 else h


def sleep_reference(age_years: float) -> tuple[str, int, int | None] | None:
    """CDC recommended hours for an age in years (ages 1+; under 1 year use the table directly)."""
    if age_years < 1:
        return None
    if age_years < 3:
        row = sources.SLEEP_BY_AGE[2]
    elif age_years < 6:
        row = sources.SLEEP_BY_AGE[3]
    elif age_years < 13:
        row = sources.SLEEP_BY_AGE[4]
    elif age_years < 18:
        row = sources.SLEEP_BY_AGE[5]
    elif age_years <= 60:
        row = sources.SLEEP_BY_AGE[6]
    elif age_years < 65:
        row = sources.SLEEP_BY_AGE[7]
    else:
        row = sources.SLEEP_BY_AGE[8]
    return f"{row[0]} ({row[1]})", row[2], row[3]


# ---------------------------------------------------------------------------
# Activity and habits
# ---------------------------------------------------------------------------

def weekly_activity(daily_minutes: list, goal_minutes: float | None) -> dict:
    """Total and progress from up to 7 daily entries. Blank days count as 'not logged', not as zero."""
    if len(daily_minutes) > 7:
        raise ValueError("A week has at most 7 days.")
    logged = []
    for m in daily_minutes:
        if m is None or m == "":
            continue
        m = float(m)
        if m < 0 or m > 1440:
            raise ValueError("Daily minutes must be between 0 and 1,440 (24 hours).")
        logged.append(m)
    total = sum(logged)
    progress = None
    if goal_minutes is not None:
        if goal_minutes <= 0:
            raise ValueError("Set a weekly goal above 0 minutes, or leave it blank.")
        progress = total / goal_minutes
    return {"total": total, "days_logged": len(logged), "days_not_logged": 7 - len(logged), "progress": progress}


def completion_percent(completed: float, planned: float) -> float:
    """Completed check-ins / planned check-ins x 100."""
    if planned <= 0:
        raise ValueError("Planned check-ins must be at least 1.")
    if completed < 0:
        raise ValueError("Completed check-ins cannot be negative.")
    if completed > planned:
        raise ValueError("Completed check-ins cannot be more than planned check-ins.")
    return completed / planned * 100


def progression_plan(start_minutes: float, step_minutes: float, cap_minutes: float, weeks: int = 6) -> list[float]:
    """Gentle progression: add a fixed step each week until the cap the user chose."""
    if start_minutes <= 0 or cap_minutes <= 0:
        raise ValueError("Start and cap minutes must be greater than 0.")
    if step_minutes < 0:
        raise ValueError("The weekly step cannot be negative.")
    if cap_minutes < start_minutes:
        raise ValueError("The cap must be at least the starting minutes.")
    return [min(start_minutes + step_minutes * i, cap_minutes) for i in range(weeks)]


def template_minutes(start_minutes: float, step_minutes: float, cap_minutes: float | None, start: date | None,
                     on: date) -> float:
    """Minutes planned for the week containing `on`: start + one step per full week since the start date."""
    if start is None or on < start:
        return start_minutes
    weeks = (on - start).days // 7
    planned = start_minutes + (step_minutes or 0) * weeks
    return min(planned, cap_minutes) if cap_minutes else planned
