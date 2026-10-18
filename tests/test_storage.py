import json
from datetime import date

import pytest

import sample_data
import storage

TODAY = date(2026, 10, 18)


def test_sample_data_is_valid_and_labelled():
    data = sample_data.sample_data(TODAY)
    names = {p["name"] for p in data["profiles"]}
    for key in storage.LIST_KEYS:
        assert storage.table_issues(key, data[key], TODAY, names) == [], key
        assert all(r["origin"] == storage.ORIGIN_SAMPLE for r in data[key])
    assert storage.has_sample_rows(data)


def test_profile_separation():
    data = sample_data.sample_data(TODAY)
    maya = storage.for_profiles(data["sleep_log"], "Maya")
    assert maya and all(r["profile"] == "Maya" for r in maya)
    two = storage.for_profiles(data["measurements"], ["Alex", "Leo"])
    assert {r["profile"] for r in two} == {"Alex", "Leo"}
    assert len(storage.for_profiles(data["sleep_log"], storage.EVERYONE)) == len(data["sleep_log"])
    assert storage.for_profiles(data["sleep_log"], "Nobody") == []


def test_date_filter_is_inclusive_and_skips_undated():
    rows = [{"date": "2026-10-01"}, {"date": "2026-10-10"}, {"date": "2026-10-11"}, {"date": None}]
    got = storage.in_date_range(rows, date(2026, 10, 1), date(2026, 10, 10))
    assert [r["date"] for r in got] == ["2026-10-01", "2026-10-10"]
    assert len(storage.in_date_range(rows, None, None)) == 3


def test_validation_catches_impossible_inputs():
    names = {"Alex"}
    v = lambda key, rec: storage.row_issues(key, storage.clean_records(key, [rec])[0], TODAY, names)  # noqa: E731
    assert v("measurements", {"date": "2026-10-01", "profile": "Alex", "measure": "Blood pressure", "value": 80,
                              "value2": 120, "unit": "mmHg"})
    assert v("measurements", {"date": "2026-10-01", "profile": "Alex", "measure": "Weight", "value": 70,
                              "unit": "cm"})
    assert v("measurements", {"date": "2026-10-01", "profile": "Alex", "measure": "Weight", "value": 2000,
                              "unit": "lb"})
    assert v("measurements", {"date": "2026-10-01", "profile": "Alex", "measure": "Weight", "value": 160,
                              "unit": "lb"}) == []
    assert any("future" in m for m in v("activity_log", {"date": "2026-12-01", "profile": "Alex",
                                                          "activity_type": "Walking", "minutes": 20}))
    assert v("activity_log", {"date": "2026-10-01", "profile": "Alex", "activity_type": "Walking", "minutes": 2000})
    assert v("sleep_log", {"date": "2026-10-01", "profile": "Alex", "bedtime": "23:00", "wake_time": "06:00",
                           "est_sleep_hours": 9, "mood": 6})
    assert v("meal_log", {"date": "2026-10-01", "profile": "Ghost", "food": "Apple", "grams": 100})
    assert v("appointments", {"date": "2026-12-01", "profile": "Alex"}) == []  # future appointment is fine


def test_coercion_handles_editor_values():
    rows = storage.clean_records("sleep_log", [
        {"date": "2026-10-01T00:00:00", "profile": "Alex", "bedtime": "11:30 pm", "wake_time": "6:15",
         "est_sleep_hours": "7.5", "mood": 4.0},
        {"date": None, "profile": "", "bedtime": None},  # entirely empty -> dropped
    ])
    assert len(rows) == 1
    r = rows[0]
    assert r["date"] == "2026-10-01" and r["bedtime"] == "23:30" and r["wake_time"] == "06:15"
    assert r["est_sleep_hours"] == 7.5 and r["mood"] == 4 and r["origin"] == storage.ORIGIN_USER


def test_json_round_trip_is_lossless():
    data = sample_data.sample_data(TODAY)
    data["meal_log"].append({**data["meal_log"][0], "notes": "Ünïcode ✓", "origin": storage.ORIGIN_USER})
    raw = storage.to_backup_json(data).encode("utf-8")
    restored, notes = storage.from_backup_bytes(raw)
    assert notes == []
    for key in storage.LIST_KEYS:
        assert restored[key] == data[key], key
    assert restored["settings"]["units"] == data["settings"]["units"]
    # And a second trip produces identical JSON apart from the timestamp
    again = json.loads(storage.to_backup_json(restored))
    first = json.loads(raw)
    again.pop("exported_at"), first.pop("exported_at")
    assert again == first


def test_import_rejects_bad_files_and_skips_bad_rows():
    with pytest.raises(ValueError):
        storage.from_backup_bytes(b"not json")
    with pytest.raises(ValueError):
        storage.from_backup_bytes(json.dumps({"app": "something-else"}).encode())
    payload = {"app": storage.APP_ID, "schema_version": 99, "profiles": [{"name": "Kim", "age_group": "Adult (20+)"},
                                                                         "junk", {}],
               "sleep_log": "oops", "settings": {"units": "furlongs"}}
    data, notes = storage.from_backup_bytes(json.dumps(payload).encode())
    assert [p["name"] for p in data["profiles"]] == ["Kim"]
    assert data["sleep_log"] == [] and data["settings"]["units"] == storage.DEFAULT_SETTINGS["units"]
    assert any("different app version" in n for n in notes) and any("sleep_log" in n for n in notes)


def test_remove_sample_rows_keeps_user_rows():
    data = sample_data.sample_data(TODAY)
    data["profiles"].append({"name": "Kim", "age_group": "Adult (20+)", "birth_year": None, "notes": "",
                             "origin": storage.ORIGIN_USER})
    removed = storage.remove_sample_rows(data)
    assert removed > 100
    assert [p["name"] for p in data["profiles"]] == ["Kim"]
    assert not storage.has_sample_rows(data)


def test_rename_profile_moves_every_record():
    data = sample_data.sample_data(TODAY)
    before = len(storage.for_profiles(data["sleep_log"], "Alex"))
    storage.rename_profile(data, "Alex", "Sam")
    assert len(storage.for_profiles(data["sleep_log"], "Sam")) == before
    assert storage.for_profiles(data["sleep_log"], "Alex") == []
    assert "Sam" in [p["name"] for p in data["profiles"]]


def test_bundled_sample_backup_imports_cleanly():
    from pathlib import Path
    raw = (Path(__file__).resolve().parents[1] / "data" / "sample-family-backup.json").read_bytes()
    data, notes = storage.from_backup_bytes(raw)
    assert notes == [] and len(data["profiles"]) == 4
