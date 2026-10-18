from datetime import date, timedelta

import pandas as pd

import charts
import insights
import reminders
import sample_data
import storage

TODAY = date(2026, 10, 18)


def test_insufficient_data_message():
    data = storage.empty_data()
    obs = insights.observations(data, "Alex", TODAY)
    assert any("not enough nights" in o["text"] for o in obs)
    assert any("nothing logged yet" in o["text"] for o in obs)


def test_sleep_observation_wording_and_numbers():
    data = storage.empty_data()
    for back in range(1, 15):
        hours_end = "05:30" if back <= 7 else "07:00"  # less sleep in the last 7 nights
        data["sleep_log"].append({"date": (TODAY - timedelta(days=back)).isoformat(), "profile": "Alex",
                                  "bedtime": "23:00", "wake_time": hours_end, "est_sleep_hours": None})
    data["sleep_log"] = storage.clean_records("sleep_log", data["sleep_log"])
    texts = [o["text"] for o in insights.observations(data, "Alex", TODAY)]
    assert any(t.startswith("You logged less sleep") and "6.5 h" in t and "8.0 h" in t for t in texts)
    assert not any("insomnia" in t.lower() or "because" in t.lower() for t in texts)


def test_unlogged_days_are_not_counted_as_missed():
    data = storage.empty_data()
    data["habits"] = storage.clean_records("habits", [{"profile": "Alex", "habit": "Walk", "days_per_week": 5}])
    hw = insights.habit_week(data, "Alex", "Walk", insights.week_start(TODAY), TODAY)
    assert hw["percent"] is None  # nothing logged -> unknown, not 0%
    data["habit_log"] = storage.clean_records("habit_log", [{"date": "2026-10-13", "profile": "Alex",
                                                             "habit": "Walk", "done": True}])
    hw = insights.habit_week(data, "Alex", "Walk", insights.week_start(TODAY), TODAY)
    assert hw["percent"] == 20 and hw["not_logged"] == 6


def test_priorities_order_and_profile_filter():
    data = sample_data.sample_data(TODAY)
    pri = insights.priorities(data, TODAY)
    assert pri[0]["level"] == "Overdue" and "Leo" in pri[0]["text"]
    only_maya = insights.priorities(data, TODAY, profiles="Maya")
    assert only_maya and all(p["text"].startswith("Maya") for p in only_maya)


def test_upcoming_skips_done_and_unconfirmed_tasks():
    data = sample_data.sample_data(TODAY)
    items = reminders.upcoming(data, TODAY, days_ahead=30)
    titles = [i["title"] for i in items]
    assert "Return school sports form" not in titles  # not confirmed
    data["care_tasks"][0]["done"] = True
    assert data["care_tasks"][0]["task"] not in [i["title"] for i in reminders.upcoming(data, TODAY, 30)]


def test_ics_file_is_well_formed_and_can_hide_details():
    data = sample_data.sample_data(TODAY)
    items = reminders.upcoming(data, TODAY, 30)
    ics = reminders.to_ics(items)
    assert ics.startswith("BEGIN:VCALENDAR\r\n") and ics.endswith("END:VCALENDAR\r\n")
    assert ics.count("BEGIN:VEVENT") == len(items)
    assert all(len(line.encode()) <= 75 for line in ics.split("\r\n"))
    assert "DTSTART:" in ics and "DTSTART;VALUE=DATE:" in ics
    private = reminders.to_ics(items, private_titles=True)
    assert "Alex" not in private and "SUMMARY:Health reminder" in private


def test_daily_series_shows_gaps_not_zeros():
    df = pd.DataFrame({"date": ["2026-10-01", "2026-10-01", "2026-10-03"], "profile": ["A", "A", "A"],
                       "minutes": [10, 20, 30]})
    out = charts.daily_series(df, "minutes", date(2026, 10, 1), date(2026, 10, 4))
    assert list(out["minutes"].fillna(-1)) == [30, -1, 30, -1]


def test_long_gaps_break_lines_and_averages_do_not_fill():
    df = pd.DataFrame({"date": pd.to_datetime(["2026-08-01", "2026-08-05", "2026-09-30"]), "profile": "A",
                       "value": [80.0, 81.0, 82.0]})
    broken = charts.break_long_gaps(df, ["value"])
    assert len(broken) == 4 and broken["value"].isna().sum() == 1
    avg = charts.rolling_average(df, "value", days=7, min_periods=2)
    assert len(avg) == 3  # one average point per real reading, no invented dates
    assert avg["avg"].isna().sum() == 2  # not enough readings in those windows -> no average
