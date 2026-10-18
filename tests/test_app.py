from datetime import date

from streamlit.testing.v1 import AppTest

APP = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "app.py")


def run():
    return AppTest.from_file(APP, default_timeout=90).run()


def no_errors(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_app_starts_with_sample_data_and_all_tabs():
    at = run()
    no_errors(at)
    labels = [t.label for t in at.tabs]
    for name in ["🏠 Today", "🥗 Nutrition & Meals", "🚶 Fitness & Movement", "🌙 Sleep & Wellbeing",
                 "📁 Health Records & Care", "📊 Trends", "🧮 Calculators"]:
        assert name in labels
    assert any("Sample data is showing" in i.value for i in at.info)
    assert any("Rule-based observations" in m.value for m in at.markdown)


def test_start_empty_then_reload_sample():
    at = run()
    next(b for b in at.button if "Start empty" in b.label).click().run()
    no_errors(at)
    assert at.session_state["data"]["profiles"] == []
    assert not any("Sample data is showing" in i.value for i in at.info)
    assert any("No family members yet" in i.value for i in at.info)
    next(b for b in at.button if "Load sample family" in b.label).click().run()
    no_errors(at)
    assert len(at.session_state["data"]["profiles"]) == 4


def test_family_member_filter_separates_profiles():
    at = run()
    at.selectbox(key="who").set_value("Maya").run()
    no_errors(at)
    editors = [d.value for d in at.dataframe if "origin" in d.value.columns and "profile" in d.value.columns]
    assert len(editors) >= 10
    checked = 0
    for df in editors:
        if len(df):
            assert set(df["profile"]) == {"Maya"}
            checked += 1
    assert checked >= 5
    # Records for other people are still kept in session, just not shown
    assert {r["profile"] for r in at.session_state["data"]["sleep_log"]} >= {"Alex", "Jordan", "Maya"}


def test_remove_sample_rows_only():
    at = run()
    next(b for b in at.button if "Remove sample rows" in b.label).click().run()
    no_errors(at)
    assert all(not rows for k, rows in at.session_state["data"].items() if k != "settings")


def test_calculators_validate_inputs():
    at = run()
    at.number_input[0].set_value(0.0).run()  # impossible weight on the BMI calculator
    assert any("Weight must be between" in e.value for e in at.error)
