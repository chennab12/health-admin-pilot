"""Rule-based observations and Today's priorities.

These are plain Python rules, not AI and not medical advice. Each one says
what was logged and compares it with the person's own goals or earlier
entries. Nothing here guesses causes or names conditions. Days without
entries are treated as "not logged", never as "did not happen".
"""

from __future__ import annotations

from datetime import date, timedelta

import calculations as calc
import foods
import reminders
import storage

MIN_ENTRIES = 3  # fewer entries than this in a window -> "not enough data"


# ---------------------------------------------------------------------------
# Shared helpers (also used by the Trends tab)
# ---------------------------------------------------------------------------

def sleep_rows(records: list[dict]) -> list[dict]:
    """Add time in bed and the sleep figure used for summaries.

    The person's own estimate is used when given; otherwise time in bed is used and labelled as such.
    """
    out = []
    for r in records:
        row = dict(r)
        try:
            row["hours_in_bed"] = calc.sleep_hours(r.get("bedtime"), r.get("wake_time"))
        except ValueError:
            row["hours_in_bed"] = None
        if r.get("est_sleep_hours") is not None:
            row["sleep_hours"], row["sleep_basis"] = r["est_sleep_hours"], "Your estimate"
        elif row["hours_in_bed"] is not None:
            row["sleep_hours"], row["sleep_basis"] = row["hours_in_bed"], "Time in bed"
        else:
            row["sleep_hours"], row["sleep_basis"] = None, "Not enough information"
        row["bed_axis"] = calc.bedtime_axis_hours(r.get("bedtime")) if r.get("bedtime") else None
        out.append(row)
    return out


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _window(records, today, start_back, end_back, field="date"):
    start = today - timedelta(days=end_back)
    end = today - timedelta(days=start_back)
    return storage.in_date_range(records, start, end, field)


def _avg(values):
    vals = [v for v in values if v is not None]
    return sum(vals) / len(vals) if vals else None


def habit_week(data: dict, profile: str, habit: str, week_monday: date, today: date) -> dict:
    """Check-ins for one habit in one calendar week."""
    target = next((h.get("days_per_week") for h in data.get("habits", [])
                   if h.get("profile") == profile and h.get("habit") == habit), None) or 7
    end = min(week_monday + timedelta(days=6), today)
    logs = [r for r in storage.in_date_range(data.get("habit_log", []), week_monday, end)
            if r.get("profile") == profile and r.get("habit") == habit]
    done_days = len({r["date"] for r in logs if r.get("done")})
    logged_days = len({r["date"] for r in logs})
    days_so_far = (end - week_monday).days + 1
    pct = None if logged_days == 0 else min(done_days, target) / target * 100
    return {"target": target, "done": done_days, "logged_days": logged_days,
            "not_logged": max(days_so_far - logged_days, 0), "percent": pct}


def activity_week(data: dict, profile: str, week_monday: date, today: date) -> dict:
    end = min(week_monday + timedelta(days=6), today)
    rows = [r for r in storage.valid_records("activity_log", data.get("activity_log", []), today)
            if r.get("profile") == profile]
    rows = storage.in_date_range(rows, week_monday, end)
    return {
        "minutes": sum(r.get("minutes") or 0 for r in rows),
        "strength": len({r["date"] for r in rows if r.get("activity_type") == "Strength"}),
        "mobility": len({r["date"] for r in rows if r.get("activity_type") == "Mobility"}),
        "days_logged": len({r["date"] for r in rows}),
        "days_so_far": (end - week_monday).days + 1,
        "steps_days": [r.get("steps") for r in rows if r.get("steps") is not None],
    }


# ---------------------------------------------------------------------------
# Observations
# ---------------------------------------------------------------------------

def observations(data: dict, profile: str, today: date) -> list[dict]:
    """Short, factual comparisons for one person. Each has 'kind' (info or note) and 'text'."""
    out: list[dict] = []
    obs = lambda text, kind="info": out.append({"kind": kind, "text": text})  # noqa: E731

    # Sleep: last 7 nights vs the 7 before.
    sl = sleep_rows([r for r in storage.valid_records("sleep_log", data.get("sleep_log", []), today)
                     if r.get("profile") == profile])
    this, last = _window(sl, today, 1, 7), _window(sl, today, 8, 14)
    this_h = [r["sleep_hours"] for r in this if r["sleep_hours"] is not None]
    last_h = [r["sleep_hours"] for r in last if r["sleep_hours"] is not None]
    if len(this_h) < MIN_ENTRIES or len(last_h) < MIN_ENTRIES:
        obs(f"Sleep: not enough nights logged to compare weeks ({len(this_h)} in the last 7 nights, "
            f"{len(last_h)} in the 7 before; {MIN_ENTRIES} each are needed).", "note")
    else:
        a, b = _avg(this_h), _avg(last_h)
        if a < b - 0.5:
            obs(f"You logged less sleep in the last 7 nights: about {a:.1f} h a night over {len(this_h)} nights, "
                f"compared with {b:.1f} h over {len(last_h)} nights the week before.")
        elif a > b + 0.5:
            obs(f"You logged more sleep in the last 7 nights: about {a:.1f} h a night over {len(this_h)} nights, "
                f"compared with {b:.1f} h the week before.")
        else:
            obs(f"Logged sleep was similar to the week before (about {a:.1f} h vs {b:.1f} h a night).")
        beds_a = _avg([r["bed_axis"] for r in this])
        beds_b = _avg([r["bed_axis"] for r in last])
        if beds_a is not None and beds_b is not None and abs(beds_a - beds_b) >= 0.5:
            word = "later" if beds_a > beds_b else "earlier"
            obs(f"Logged bedtimes were {word} this week (average {calc.clock_label(beds_a)} vs "
                f"{calc.clock_label(beds_b)}).")

    # Mood and energy averages.
    for field in ("energy", "mood"):
        a = [r.get(field) for r in this if r.get(field) is not None]
        b = [r.get(field) for r in last if r.get(field) is not None]
        if len(a) >= MIN_ENTRIES and len(b) >= MIN_ENTRIES and abs(_avg(a) - _avg(b)) >= 0.5:
            word = "higher" if _avg(a) > _avg(b) else "lower"
            obs(f"Your logged {field} ratings were {word} this week ({_avg(a):.1f} vs {_avg(b):.1f} out of 5). "
                "This describes your entries only, not a cause.")

    # Activity vs the person's own goal (current calendar week).
    goal = next((g for g in data.get("activity_goals", []) if g.get("profile") == profile), None)
    wk = activity_week(data, profile, week_start(today), today)
    if goal and goal.get("weekly_minutes"):
        obs(f"Activity this week: {wk['minutes']:.0f} of your {goal['weekly_minutes']:.0f}-minute goal logged, "
            f"on {wk['days_logged']} of {wk['days_so_far']} days so far. Days without entries count as not logged.")
    elif wk["days_logged"]:
        obs(f"Activity this week: {wk['minutes']:.0f} minutes logged on {wk['days_logged']} days. "
            "Set a weekly goal in Fitness & Movement to track progress.")
    else:
        obs("Activity: nothing logged yet this week.", "note")
    if goal and goal.get("strength_sessions"):
        obs(f"Strength sessions this week: {wk['strength']} of {goal['strength_sessions']} planned.")

    # Habits: this calendar week.
    for h in data.get("habits", []):
        if h.get("profile") != profile or not h.get("active"):
            continue
        hw = habit_week(data, profile, h["habit"], week_start(today), today)
        if hw["percent"] is None:
            obs(f"Habit '{h['habit']}': no check-ins logged this week.", "note")
        else:
            obs(f"Habit '{h['habit']}': done on {hw['done']} day(s) this week, plan is {hw['target']} "
                f"({hw['percent']:.0f}% of plan); {hw['not_logged']} day(s) not logged.")

    # Nutrition: fiber vs own goal, logged days only.
    ng = next((g for g in data.get("nutrition_goals", []) if g.get("profile") == profile), None)
    logs = _window([r for r in storage.valid_records("meal_log", data.get("meal_log", []), today)
                    if r.get("profile") == profile], today, 0, 6)
    if ng and ng.get("fiber_g") and logs:
        rows = foods.meal_log_nutrition(logs, data.get("custom_foods"))
        by_day: dict[str, list] = {}
        for r in rows:
            by_day.setdefault(r["date"], []).append(r)
        totals = [foods.total_nutrition(v)["fiber_g"] for v in by_day.values()]
        known = [t["total"] for t in totals if t["total"] is not None]
        missing = sum(t["missing"] for t in totals)
        if len(known) >= MIN_ENTRIES:
            extra = f" {missing} logged item(s) had no fiber data, so the real figure may be higher." if missing else ""
            obs(f"Estimated fiber on {len(known)} logged days averaged {_avg(known):.0f} g, compared with your own "
                f"goal of {ng['fiber_g']:.0f} g.{extra}")
        else:
            obs("Nutrition: fewer than 3 days of meals logged this week, so no average is shown.", "note")
    return out


# ---------------------------------------------------------------------------
# Today's priorities
# ---------------------------------------------------------------------------

def priorities(data: dict, today: date, profiles=None, limit: int = 6) -> list[dict]:
    """Ordered list of {'level', 'text', 'rule', 'origin'}. Rules are listed in the app."""
    out = []
    for it in reminders.upcoming(data, today, days_ahead=7, profiles=profiles):
        if it["overdue"]:
            level, rank = "Overdue", 0
        elif it["kind"] == "Appointment" and it["days"] <= 2:
            level, rank = "Soon", 1
        elif it["kind"] == "Refill" and it["days"] <= 7:
            level, rank = "Soon", 2
        elif it["days"] == 0:
            level, rank = "Today", 1
        else:
            level, rank = "This week", 3
        when = "today" if it["days"] == 0 else (f"{-it['days']} day(s) overdue" if it["overdue"]
                                                else f"in {it['days']} day(s)")
        out.append({"rank": rank, "level": level, "text": f"{it['profile']}: {it['title']} ({when})",
                    "rule": RULES[it["kind"]], "origin": it.get("origin")})
    names = [p["name"] for p in storage.for_profiles(data.get("profiles", []), profiles, field="name")]
    logged_today = {(r.get("profile"), r.get("habit")) for r in data.get("habit_log", [])
                    if r.get("date") == today.isoformat()}
    for h in data.get("habits", []):
        if h.get("active") and h.get("profile") in names and (h["profile"], h["habit"]) not in logged_today:
            out.append({"rank": 4, "level": "Today", "text": f"{h['profile']}: check in on '{h['habit']}'",
                        "rule": RULES["habit"], "origin": h.get("origin")})
    last_night = (today - timedelta(days=1)).isoformat()
    sleepers = {r.get("profile") for r in data.get("sleep_log", []) if r.get("date") == last_night}
    for p in data.get("sleep_plan", []):
        if p.get("profile") in names and p["profile"] not in sleepers:
            out.append({"rank": 5, "level": "Today", "text": f"{p['profile']}: log last night's sleep (optional)",
                        "rule": RULES["sleep"], "origin": p.get("origin")})
    out.sort(key=lambda r: r["rank"])
    return out[:limit]


RULES = {
    "Care task": "Confirmed care task that is not done and is overdue or due within 7 days.",
    "Appointment": "Appointment within 7 days (marked 'Soon' within 2 days).",
    "Refill": "Active medication with a refill date you entered within 7 days, or past.",
    "Vaccination due": "A next-due date you recorded for a vaccine, within 7 days or past.",
    "habit": "An active habit with no check-in yet today.",
    "sleep": "A sleep plan exists but no sleep entry for last night.",
}
