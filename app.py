"""Family Health & Wellness Copilot.

A Streamlit organizer for family wellness routines, meals, activity, sleep,
appointments and health records. Everything is plain Python rules: there is
no AI, no API key, no login and no database. Records live in this browser
session only and can be saved and restored as a JSON file.

This is an organizer, not an emergency, monitoring or diagnostic service.
"""

from __future__ import annotations

import copy
import io
from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st

import calculations as calc
import charts
import foods
import insights
import reminders
import sample_data
import sources
import storage

st.set_page_config(page_title="Family Health & Wellness Copilot", page_icon="🌿", layout="wide",
                   initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
      .block-container {padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1200px;}
      div[data-testid="stMetricValue"] {font-size: 1.5rem;}
      .badge {display:inline-block; padding:1px 8px; border-radius:999px; font-size:0.78rem; line-height:1.5;
              border:1px solid rgba(128,128,128,.5); margin-right:4px; white-space:nowrap;}
      .b-red {background:rgba(227,73,72,.14);} .b-amber {background:rgba(237,161,0,.18);}
      .b-blue {background:rgba(42,120,214,.14);} .b-green {background:rgba(27,175,122,.16);}
      .b-gray {background:rgba(128,128,128,.12);}
      .clinician {border-left:4px solid #6250d6; padding:.4rem .8rem; margin:.3rem 0;
                  background:rgba(98,80,214,.07); border-radius:4px;}
      @media (max-width: 640px) {
        .block-container {padding-left: .9rem; padding-right: .9rem; padding-top: 1.2rem;}
        div[data-testid="stMetricValue"] {font-size: 1.2rem;}
        h1 {font-size: 1.45rem !important;}
        h2, h3 {font-size: 1.15rem !important;}
        button[data-baseweb="tab"], [role="tab"] {padding-left: .4rem; padding-right: .4rem;}
      }
    </style>
    """,
    unsafe_allow_html=True,
)

ss = st.session_state
TODAY = date.today()
EVERYONE = storage.EVERYONE


# ---------------------------------------------------------------------------
# Session state: `data` holds current records, `base` feeds the editors.
# Editors keep their own changes until commit() copies data -> base and bumps
# the version, so every editor restarts from the current records.
# ---------------------------------------------------------------------------

def commit(message: str | None = None) -> None:
    ss.base = copy.deepcopy(ss.data)
    ss.ver += 1
    if message:
        ss.flash = message


def set_data(data: dict, message: str) -> None:
    ss.data = data
    ss.units = data["settings"].get("units", storage.DEFAULT_SETTINGS["units"])
    ss.who = EVERYONE
    commit(message)


if "data" not in ss:
    ss.data = sample_data.sample_data(TODAY)
    ss.base = copy.deepcopy(ss.data)
    ss.ver = 0
    ss.units = ss.data["settings"]["units"]
    ss.who = EVERYONE

data = ss.data
data["settings"]["units"] = ss.get("units", storage.DEFAULT_SETTINGS["units"])
METRIC = data["settings"]["units"].startswith("Metric")
W_UNIT, L_UNIT = ("kg", "cm") if METRIC else ("lb", "in")


def names() -> list[str]:
    return [p["name"] for p in data.get("profiles", []) if p.get("name")]


COLORS = charts.profile_colors(names())


# ---------------------------------------------------------------------------
# Small display helpers
# ---------------------------------------------------------------------------

def badge(text: str, tone: str = "gray") -> str:
    return f'<span class="badge b-{tone}">{text}</span>'


def origin_badge(origin: str | None) -> str:
    return badge("📋 Sample", "gray") if origin == storage.ORIGIN_SAMPLE else badge("✍️ Yours", "blue")


def html(text: str) -> None:
    st.markdown(text, unsafe_allow_html=True)


def esc(text) -> str:
    return (str(text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("$", "&#36;"))


def csv_button(df: pd.DataFrame, filename: str, label: str = "⬇️ Download CSV", key: str | None = None) -> None:
    st.download_button(label, df.to_csv(index=False).encode("utf-8"), filename, "text/csv",
                       key=key or f"dl_{filename}_{ss.ver}",
                       help="CSV files contain personal health information. Store them privately.")


def fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    d = date.fromisoformat(iso)
    return d.strftime("%a %b %d").replace(" 0", " ")


def sample_banner() -> None:
    if storage.has_sample_rows(data):
        st.info("📋 **Sample data is showing.** These are made-up records for a synthetic family. "
                "Rows marked *Sample* are demo data; rows marked *Yours* are what you entered. "
                "Use **Start empty** (top of the page) before adding real information.", icon="ℹ️")


def weight_to_display(value: float, unit: str) -> float:
    kg = calc.to_kg(value, unit)
    return kg if METRIC else calc.kg_to_lb(kg)


def length_to_display(value: float, unit: str) -> float:
    cm = calc.to_cm(value, unit)
    return cm if METRIC else calc.cm_to_in(cm)


# ---------------------------------------------------------------------------
# Editable tables
# ---------------------------------------------------------------------------

def records_frame(key: str, records: list[dict]) -> pd.DataFrame:
    """Typed DataFrame for st.data_editor (dates as datetimes, times as time objects)."""
    schema = storage.SCHEMAS[key]
    cols = list(schema) + ["origin"]
    df = pd.DataFrame(records, columns=cols)
    for field, kind in schema.items():
        if kind == "date":
            df[field] = pd.to_datetime(df[field], errors="coerce")
        elif kind == "time":
            df[field] = df[field].map(lambda v: storage.time_value(v) if isinstance(v, str) and v else None)
            df[field] = df[field].astype(object)
        elif kind in ("float", "int"):
            df[field] = pd.to_numeric(df[field], errors="coerce").astype(float)
        elif kind == "bool":
            df[field] = df[field].map(lambda v: bool(v) if v is not None and not pd.isna(v) else False).astype(bool)
        else:
            df[field] = df[field].fillna("").astype(str)
    df["origin"] = df["origin"].fillna(storage.ORIGIN_USER).astype(str)
    return df


def _signature(rec: dict) -> tuple:
    return tuple(sorted((k, v) for k, v in rec.items() if k != "origin"))


def edit_table(key: str, config: dict, profile_filter: bool = True, height="auto", defaults: dict | None = None,
               sort_by: str | None = None) -> list[dict]:
    """Show an editable table. Filtered to the chosen family member when profile_filter is True.

    Returns the cleaned rows that are shown. Edited sample rows become 'Yours'.
    """
    schema = storage.SCHEMAS[key]
    base = ss.base.get(key, [])
    who = ss.get("who", EVERYONE)
    use_filter = profile_filter and "profile" in schema and who != EVERYONE
    shown = [r for r in base if r.get("profile") == who] if use_filter else list(base)
    others = [r for r in base if r.get("profile") != who] if use_filter else []
    if sort_by:
        shown = sorted(shown, key=lambda r: str(r.get(sort_by) or ""), reverse=True)
    df = records_frame(key, shown)
    cfg = {"origin": st.column_config.TextColumn("Source", disabled=True, width="small",
                                                 help="Sample = demo data. You = entered or edited by you.")}
    cfg.update(config)
    edited = st.data_editor(df, key=f"ed_{key}_{who if use_filter else 'all'}_{ss.ver}", column_config=cfg,
                            num_rows="dynamic", hide_index=True, width="stretch", height=height,
                            column_order=list(schema) + ["origin"])
    rows = edited.to_dict("records")
    fill = dict(defaults or {})
    if use_filter:
        fill.setdefault("profile", who)
    for r in rows:
        is_new = not r.get("origin") or r.get("origin") == "nan"
        for f, v in fill.items():
            if is_new and (r.get(f) is None or r.get(f) == "" or (isinstance(r.get(f), float) and pd.isna(r[f]))):
                r[f] = v
    cleaned = storage.clean_records(key, rows)
    original = {_signature(r) for r in shown}
    for r in cleaned:
        if r["origin"] == storage.ORIGIN_SAMPLE and _signature(r) not in original:
            r["origin"] = storage.ORIGIN_USER
    data[key] = others + cleaned
    problems = storage.table_issues(key, cleaned, TODAY, set(names()))
    if problems:
        with st.container(border=True):
            st.markdown(f"⚠️ **{len(problems)} thing(s) to check** (these rows are left out of totals and charts "
                        "until fixed):")
            for p in problems[:8]:
                st.markdown(f"- {p}")
            if len(problems) > 8:
                st.caption(f"…and {len(problems) - 8} more.")
    return cleaned


def profile_col(label: str = "Family member", extra: list[str] | None = None):
    return st.column_config.SelectboxColumn(label, options=(extra or []) + names(), required=True)


def date_col(label: str = "Date", **kw):
    return st.column_config.DateColumn(label, format="YYYY-MM-DD", **kw)


def time_col(label: str, **kw):
    return st.column_config.TimeColumn(label, format="HH:mm", step=60, **kw)


def num_col(label: str, lo=None, hi=None, step=1.0, fmt="%g", **kw):
    return st.column_config.NumberColumn(label, min_value=lo, max_value=hi, step=step, format=fmt, **kw)


def text_col(label: str, **kw):
    return st.column_config.TextColumn(label, **kw)


def check_col(label: str, **kw):
    return st.column_config.CheckboxColumn(label, **kw)


def valid(key: str) -> list[dict]:
    return storage.valid_records(key, data.get(key, []), TODAY)


def chosen(records: list[dict], field: str = "profile") -> list[dict]:
    return storage.for_profiles(records, ss.get("who", EVERYONE), field)


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------

def cb_start_empty():
    set_data(storage.empty_data(), "Started empty. Add family members under 📁 Health Records & Care → Profiles.")


def cb_load_sample():
    set_data(sample_data.sample_data(TODAY), "Loaded the synthetic sample family.")


def cb_remove_sample():
    n = storage.remove_sample_rows(ss.data)
    ss.data["settings"]["is_sample"] = False
    ss.who = EVERYONE
    commit(f"Removed {n} sample row(s). Your own entries were kept.")


def cb_restore():
    upload = ss.get(f"restore_{ss.ver}")
    if upload is None:
        ss.flash_error = "Choose a JSON backup file first."
        return
    try:
        restored, notes = storage.from_backup_bytes(upload.getvalue())
    except ValueError as exc:
        ss.flash_error = str(exc)
        return
    set_data(restored, "Restored records from your backup. " + " ".join(notes))


def cb_filter_change():
    commit()


def cb_habit(profile: str, habit: str, widget_key: str):
    done = bool(ss.get(widget_key))
    log = [r for r in ss.data["habit_log"]
           if not (r.get("date") == TODAY.isoformat() and r.get("profile") == profile and r.get("habit") == habit)]
    log.append({"date": TODAY.isoformat(), "profile": profile, "habit": habit, "done": done,
                "origin": storage.ORIGIN_USER})
    ss.data["habit_log"] = log
    commit()


def cb_rename(old_key: str, new_key: str):
    old, new = ss.get(old_key), (ss.get(new_key) or "").strip()
    if not old or not new:
        ss.flash_error = "Pick a profile and type the new name."
        return
    if new in names():
        ss.flash_error = f"There is already a profile called '{new}'."
        return
    n = storage.rename_profile(ss.data, old, new)
    ss.who = EVERYONE
    commit(f"Renamed '{old}' to '{new}' in {n} row(s).")


# ---------------------------------------------------------------------------
# Header, data controls and the family-member filter
# ---------------------------------------------------------------------------

st.title("🌿 Family Health & Wellness Copilot")
st.caption("An organizer for routines, meals, activity, sleep, appointments and records. **Rule-based, no AI.** "
           "It is **not** an emergency, monitoring or diagnostic service and does not give medical advice. "
           "In an emergency, call your local emergency number (911 in the US).")

with st.container():  # always present, so messages never shift the tabs
    if ss.get("flash"):
        st.success(ss.pop("flash"), icon="✅")
    if ss.get("flash_error"):
        st.error(ss.pop("flash_error"), icon="⚠️")

top1, top2, top3 = st.columns([2, 1, 1])
options = [EVERYONE] + names()
if ss.get("who") not in options:
    ss.who = EVERYONE
top1.selectbox("👤 Family member", options, key="who", on_change=cb_filter_change,
               help="Filters Today, Nutrition, Fitness, Sleep and Records to one person. Everyone shows all.")
if storage.has_sample_rows(data):
    top2.button("🧹 Start empty", on_click=cb_start_empty, type="primary", width="stretch",
                help="Removes everything, including anything you typed. Export first if you want to keep it.")
    top3.button("Remove sample rows only", on_click=cb_remove_sample, width="stretch",
                help="Deletes rows marked Sample and keeps rows marked Yours.")
else:
    top2.button("📋 Load sample family", on_click=cb_load_sample, width="stretch",
                help="Replaces everything in this session with synthetic demo records.")

with st.expander("🔐 Your data, privacy and backup", expanded=False):
    st.markdown(
        "- **Not saved permanently.** Records live only in this browser session. They can be lost when the "
        "page reloads, the app restarts or the session times out. **Download a JSON backup** to keep them.\n"
        "- **Nothing is sent anywhere.** No AI services, analytics or external databases receive your entries.\n"
        "- **No family sharing or login** in this version. Each browser session is separate; to share, pass "
        "a backup file to someone you trust.\n"
        "- **Exported files contain sensitive health information.** Store them privately and never commit "
        "them to GitHub or a shared folder.\n"
        "- **Collect only what helps.** A first name or nickname and a birth year are enough. No dates of "
        "birth, addresses, insurance numbers or record numbers are needed."
    )
    b1, b2 = st.columns(2)
    b1.download_button("⬇️ Download JSON backup", storage.to_backup_json(data).encode("utf-8"),
                       f"family-health-backup-{TODAY.isoformat()}.json", "application/json", width="stretch",
                       help="Contains personal health information.")
    b2.radio("Units", ["US (lb, in)", "Metric (kg, cm)"], key="units", horizontal=True,
             help="How weights and lengths are shown in charts. Entries keep the unit you typed.")
    st.file_uploader("Restore a JSON backup (replaces everything in this session)", type=["json"],
                     key=f"restore_{ss.ver}")
    st.button("♻️ Restore from backup", on_click=cb_restore)

tab_today, tab_food, tab_fit, tab_sleep, tab_records, tab_trends, tab_calc = st.tabs(
    ["🏠 Today", "🥗 Nutrition & Meals", "🚶 Fitness & Movement", "🌙 Sleep & Wellbeing",
     "📁 Health Records & Care", "📊 Trends", "🧮 Calculators"])

# The tabs that edit records are rendered first in code, so Today and Trends see this run's edits.

# ===========================================================================
# 5. Health Records & Care
# ===========================================================================

with tab_records:
    sample_banner()
    st.subheader("📁 Health Records & Care")
    st.caption("Record what clinicians told you and what you measured. The app stores and organizes it; "
               "it does not interpret results, recommend doses or change anything a clinician said.")
    sub = st.tabs(["👪 Profiles", "📏 Measurements", "🩺 Visits & instructions", "💉 Vaccinations",
                   "💊 Medications", "✅ Tasks, appointments & reminders", "📋 Appointment prep", "📄 Read a PDF"])

    with sub[0]:
        st.markdown("Each family member has a separate profile. Records are linked by profile name.")
        before = [p.get("name") for p in ss.base.get("profiles", [])]
        edit_table("profiles", {
            "name": text_col("First name or nickname", required=True, max_chars=40),
            "age_group": st.column_config.SelectboxColumn("Age group", options=storage.AGE_GROUPS, required=True,
                                                          help="Adult BMI categories are only shown for adults 20+."),
            "birth_year": num_col("Birth year (optional)", 1900, TODAY.year, 1, "%d"),
            "notes": text_col("Notes"),
        }, profile_filter=False)
        if [p.get("name") for p in data["profiles"]] != before:
            commit()
            st.rerun()
        if names():
            with st.expander("✏️ Rename a family member everywhere"):
                r1, r2, r3 = st.columns([1, 1, 1])
                r1.selectbox("Current name", names(), key="rename_old")
                r2.text_input("New name", key="rename_new", max_chars=40)
                r3.button("Rename", on_click=cb_rename, args=("rename_old", "rename_new"), width="stretch")
            orphan = sorted({r.get("profile") for k in storage.LIST_KEYS if "profile" in storage.SCHEMAS[k]
                             for r in data[k] if r.get("profile") and r.get("profile") not in names()})
            if orphan:
                st.warning(f"Some records belong to names that are not profiles: {', '.join(orphan)}. "
                           "Add a profile with that name or edit those rows.")
        else:
            st.info("👋 Start by adding a family member: click the **+** under the table, type a name and pick "
                    "an age group.")

    with sub[1]:
        st.markdown("Enter readings as you took them. Weight in **kg or lb**, height and waist in **cm or in**, "
                    "blood pressure as **systolic in Value** and **diastolic in Value 2** (mmHg).")
        edit_table("measurements", {
            "date": date_col(required=True),
            "profile": profile_col(),
            "measure": st.column_config.SelectboxColumn("Measure", options=list(storage.MEASURES), required=True),
            "value": num_col("Value", 0, 1000, 0.1, "%.1f", help="Blood pressure: the top number (systolic)."),
            "value2": num_col("Value 2", 0, 300, 1.0, "%.0f", help="Blood pressure only: the bottom number."),
            "unit": st.column_config.SelectboxColumn("Unit", options=storage.UNITS),
            "notes": text_col("Notes", help="For example: home cuff, morning, after rest."),
        }, defaults={"date": TODAY.isoformat()}, sort_by="date", height=320)
        st.caption("The app shows these readings in 📊 Trends without labelling them high, low, good or bad.")

    with sub[2]:
        st.markdown("##### 🩺 Visits")
        edit_table("visits", {
            "date": date_col(required=True), "profile": profile_col(),
            "clinician": text_col("Clinician or clinic"), "reason": text_col("Reason"),
            "summary": text_col("What was discussed (your words)"), "follow_up": text_col("Follow-up"),
        }, sort_by="date")
        st.markdown("##### 🗒️ Clinician-provided instructions")
        st.caption("Type instructions exactly as your clinician gave them. They are kept separate from anything "
                   "the app suggests, and the app never edits or adds to them.")
        edit_table("instructions", {
            "date": date_col("Given on"), "profile": profile_col(), "clinician": text_col("From"),
            "instruction": text_col("Instruction (as given)", width="large"), "until": date_col("Until (optional)"),
        }, sort_by="date")
        current = [i for i in chosen(data["instructions"]) if not i.get("until") or i["until"] >= TODAY.isoformat()]
        for i in current:
            html(f'<div class="clinician">🩺 <b>{esc(i["profile"])}</b>, from {esc(i.get("clinician") or "clinician")}'
                 f' ({fmt_date(i.get("date"))}): “{esc(i.get("instruction"))}” {origin_badge(i.get("origin"))}</div>')

    with sub[3]:
        st.caption("Record vaccines from your clinic or pharmacy records. A 'next due' date is only what you "
                   "were told; the app does not work out vaccine schedules.")
        edit_table("vaccinations", {
            "date": date_col("Date given", required=True), "profile": profile_col(),
            "vaccine": text_col("Vaccine", required=True), "dose_note": text_col("Dose note (e.g. dose 1)"),
            "given_at": text_col("Where"), "next_due": date_col("Next due (as told)"),
        }, sort_by="date")

    with sub[4]:
        st.warning("💊 The app records medications **only as prescribed**. It never suggests doses, timing changes, "
                   "substitutions or stopping a medicine. Ask your clinician or pharmacist about any change.",
                   icon="⚠️")
        edit_table("medications", {
            "profile": profile_col(), "medication": text_col("Medication name", required=True),
            "prescribed_schedule": text_col("Prescribed schedule (copy from label or clinician)", width="large"),
            "prescriber": text_col("Prescriber"),
            "schedule_confirmed": check_col("I confirmed this schedule",
                                            help="Tick after checking it against the label or the prescriber."),
            "refill_date": date_col("Refill date"), "active": check_col("Active", default=True),
            "notes": text_col("Notes"),
        })
        for m in chosen([m for m in data["medications"] if m.get("active")]):
            status = (badge("✅ Schedule confirmed by you", "green") if m.get("schedule_confirmed")
                      else badge("⚠️ Schedule not confirmed", "amber"))
            refill = f" · refill {fmt_date(m.get('refill_date'))}" if m.get("refill_date") else ""
            html(f"**{esc(m['profile'])}: {esc(m['medication'])}** {status} {origin_badge(m.get('origin'))}<br>"
                 f"<small>{esc(m.get('prescribed_schedule') or 'Schedule not entered')}{refill}</small>")

    with sub[5]:
        st.markdown("##### ✅ Care tasks")
        st.caption("Tick **Confirmed** for real tasks (for example after a visit). Only confirmed, open tasks "
                   "appear on 🏠 Today.")
        edit_table("care_tasks", {
            "due_date": date_col("Due", required=True), "profile": profile_col(),
            "task": text_col("Task", required=True, width="large"), "confirmed": check_col("Confirmed", default=True),
            "done": check_col("Done"), "notes": text_col("Notes"),
        }, defaults={"confirmed": True})
        st.markdown("##### 📅 Appointments")
        edit_table("appointments", {
            "date": date_col(required=True), "time": time_col("Time"), "profile": profile_col(),
            "with_whom": text_col("With"), "purpose": text_col("Purpose"), "location": text_col("Where"),
            "prep_done": check_col("Prep done"),
        })
        st.markdown("##### 🔔 Reminders (next 30 days)")
        st.caption("Reminders show **only while this app is open**. There are no background notifications. "
                   "Download the calendar file so your own calendar app can remind you.")
        upcoming = reminders.upcoming(data, TODAY, days_ahead=30, profiles=ss.get("who"))
        if not upcoming:
            st.info("Nothing dated in the next 30 days. Add appointments, confirmed care tasks or refill dates.")
        else:
            for it in upcoming:
                tone = "red" if it["overdue"] else ("amber" if it["days"] <= 2 else "blue")
                when = ("Overdue" if it["overdue"] else ("Today" if it["days"] == 0 else f"In {it['days']} d"))
                t = f" {it['time']}" if it.get("time") else ""
                html(f"{badge(when, tone)} {badge(it['kind'])} **{esc(it['profile'])}**: {esc(it['title'])} "
                     f"<small>({fmt_date(it['date'])}{t})</small>")
            private = st.checkbox("Hide names and details in the calendar file", value=False,
                                  help="Each event will just say 'Health reminder'.")
            st.download_button("📆 Download calendar file (.ics)", reminders.to_ics(upcoming, private).encode("utf-8"),
                               f"family-health-reminders-{TODAY.isoformat()}.ics", "text/calendar",
                               help="Import into Google Calendar, Apple Calendar or Outlook.")

    with sub[6]:
        appts = chosen(sorted(data["appointments"], key=lambda a: a.get("date") or ""))
        labels = [f"{a.get('date')} · {a['profile']} · {a.get('purpose') or a.get('with_whom') or 'Appointment'}"
                  for a in appts]
        if not appts:
            st.info("Add an appointment first (Tasks, appointments & reminders).")
        else:
            pick = st.selectbox("Appointment", range(len(appts)), format_func=lambda i: labels[i])
            appt = appts[pick]
            st.markdown("**Preparation checklist** (ticks are not saved; they are for this visit)")
            for i, item in enumerate(reminders.APPOINTMENT_PREP):
                st.checkbox(item, key=f"prep_{pick}_{i}_{ss.ver}")
            st.markdown("**Questions to ask**")
            purpose = appt.get("purpose") or appt.get("with_whom") or ""
            qs = [q for q in data["questions"] if q.get("profile") == appt["profile"]
                  and (q.get("for_appointment") or "") == purpose]
            edit_table("questions", {
                "profile": profile_col(), "for_appointment": text_col("For appointment"),
                "question": text_col("Question", width="large"), "asked": check_col("Asked"),
            }, defaults={"profile": appt["profile"], "for_appointment": purpose})
            meds = [m for m in data["medications"] if m.get("profile") == appt["profile"] and m.get("active")]
            sheet = [f"Appointment: {appt.get('date')} {appt.get('time') or ''} with {appt.get('with_whom') or ''}",
                     f"For: {appt['profile']}   Purpose: {purpose}", "", "Questions:"]
            sheet += [f"  [ ] {q['question']}" for q in qs] or ["  (none yet)"]
            sheet += ["", "Current medications (as prescribed):"]
            sheet += [f"  - {m['medication']}: {m.get('prescribed_schedule') or 'schedule not entered'}"
                      for m in meds] or ["  (none recorded)"]
            sheet += ["", "Checklist:"] + [f"  [ ] {x}" for x in reminders.APPOINTMENT_PREP]
            st.download_button("🖨️ Download prep sheet (.txt)", "\n".join(sheet).encode("utf-8"),
                               f"appointment-prep-{appt.get('date')}.txt", "text/plain",
                               help="Contains personal health information.")

    with sub[7]:
        st.markdown("Upload a **text-based PDF** (for example a visit summary) to read its text here. "
                    "The app only extracts the text so you can copy parts into your records. It **does not "
                    "interpret** the document, and the file is not stored.")
        pdf = st.file_uploader("PDF file (max 10 MB)", type=["pdf"], key=f"pdf_{ss.ver}")
        if pdf is not None:
            try:
                from pypdf import PdfReader
                reader = PdfReader(io.BytesIO(pdf.getvalue()))
                if reader.is_encrypted:
                    raise ValueError("This PDF is password-protected. Open it in a PDF reader instead.")
                pages = [(p.extract_text() or "").strip() for p in reader.pages[:50]]
                text = "\n\n".join(f"--- Page {i + 1} ---\n{t}" for i, t in enumerate(pages) if t)
            except Exception as exc:  # pypdf raises many error types for damaged files
                st.error(f"Could not read this PDF: {exc}")
                text = None
            if text is not None:
                if not text.strip():
                    st.warning("No text found. This is probably a scanned image; this app has no OCR.")
                else:
                    st.caption(f"{len(reader.pages)} page(s), {len(text):,} characters extracted"
                               + (" (first 50 pages only)." if len(reader.pages) > 50 else "."))
                    st.text_area("Extracted text (read only)", text, height=320, disabled=True)

# ===========================================================================
# 2. Nutrition & Meals
# ===========================================================================

with tab_food:
    sample_banner()
    st.subheader("🥗 Nutrition & Meals")
    st.caption("Plan meals, build a grocery list and log what was eaten. Nutrition numbers are **estimates** "
               "from a small USDA dataset and your own entries. The app does not prescribe diets, and it "
               "**cannot tell whether a meal is allergy-safe or suitable for a medical condition**.")
    fsub = st.tabs(["📅 Weekly planner", "🛒 Grocery list", "🍽️ Meal log & estimates", "⚙️ Preferences & goals",
                    "📚 Food data"])

    with fsub[2]:
        all_food_names = sorted(set(foods.FOOD_NAMES) | {f["name"] for f in data["custom_foods"] if f.get("name")}
                                | {r.get("food") for r in ss.base["meal_log"] if r.get("food")})
        st.markdown("Log foods with **grams** (most accurate) or **portions** (uses the portion size in Food "
                    "data). Missing amounts stay missing; they are never counted as zero.")
        edit_table("meal_log", {
            "date": date_col(required=True), "profile": profile_col(),
            "meal": st.column_config.SelectboxColumn("Meal", options=storage.MEALS),
            "food": st.column_config.SelectboxColumn("Food", options=all_food_names, required=True,
                                                     help="Not listed? Add it under Preferences & goals → My foods."),
            "portions": num_col("Portions", 0, 50, 0.25, "%.2f"), "grams": num_col("Grams", 0, 5000, 1.0, "%.0f"),
            "notes": text_col("Notes"),
        }, defaults={"date": TODAY.isoformat()}, sort_by="date", height=300)

        c1, c2 = st.columns(2)
        f_start = c1.date_input("From", TODAY - timedelta(days=6), key="nut_from")
        f_end = c2.date_input("To", TODAY, key="nut_to")
        if f_start > f_end:
            st.error("'From' must be on or before 'To'.")
        else:
            logs = storage.in_date_range(chosen(valid("meal_log")), f_start, f_end)
            if not logs:
                st.info("No meals logged for this person and date range. Days without entries are shown as "
                        "'not logged', not as zero.")
            else:
                items = foods.meal_log_nutrition(logs, data["custom_foods"])
                per_day = []
                for (d_, prof), grp in pd.DataFrame(items).groupby(["date", "profile"]):
                    tot = foods.total_nutrition(grp.to_dict("records"))
                    row = {"Date": d_, "Family member": prof, "Items logged": len(grp)}
                    for n in foods.NUTRIENTS:
                        row[foods.NUTRIENT_LABELS[n]] = None if tot[n]["total"] is None else round(tot[n]["total"], 1)
                    worst = max(t["missing"] for t in tot.values())
                    row["Items without full data"] = worst
                    per_day.append(row)
                day_df = pd.DataFrame(per_day).sort_values("Date", ascending=False)
                st.markdown("**Estimated totals per logged day**")
                st.dataframe(day_df, hide_index=True, width="stretch")
                if day_df["Items without full data"].sum():
                    st.caption("⚠️ Some items had unknown amounts or nutrients, so those days' totals are "
                               "incomplete (likely underestimates). Fix them in the table above.")
                goals = {g["profile"]: g for g in data["nutrition_goals"]}
                for prof in sorted({r["profile"] for r in logs}):
                    g = goals.get(prof)
                    if not g:
                        continue
                    sub_df = day_df[day_df["Family member"] == prof]
                    parts = []
                    for n, lab in (("kcal", "kcal"), ("protein_g", "g protein"), ("fiber_g", "g fiber")):
                        col = foods.NUTRIENT_LABELS[n]
                        if g.get(n) and sub_df[col].notna().any():
                            parts.append(f"{sub_df[col].mean():.0f} of your {g[n]:.0f} {lab}")
                    if parts:
                        st.markdown(f"🎯 **{prof}**, average per logged day vs own goals: " + "; ".join(parts) + ".")
                with st.expander("Item details"):
                    item_df = pd.DataFrame(items)[["date", "profile", "meal", "food", "grams_used"] + foods.NUTRIENTS
                                                  + ["status"]].round(1)
                    st.dataframe(item_df, hide_index=True, width="stretch")
                    csv_button(item_df, "meal-log-estimates.csv")

    with fsub[0]:
        st.markdown("Plan the week. List ingredients as **Name amount unit**, separated by semicolons, for "
                    "example `Oats 160 g; Milk 500 ml; Bananas 2`. The grocery list adds them up.")
        edit_table("meal_plan", {
            "day": st.column_config.SelectboxColumn("Day", options=storage.DAYS, required=True),
            "meal": st.column_config.SelectboxColumn("Meal", options=storage.MEALS),
            "for_whom": st.column_config.SelectboxColumn("For", options=[EVERYONE] + names()),
            "dish": text_col("Dish", required=True), "prep_minutes": num_col("Prep (min)", 0, 600, 5, "%d"),
            "ingredients": text_col("Ingredients", width="large"),
        }, profile_filter=False, defaults={"for_whom": EVERYONE}, height=360)
        prefs = {p["profile"]: p for p in data["food_prefs"]}
        flags = []
        for m in data["meal_plan"]:
            who = names() if m.get("for_whom") in (None, "", EVERYONE) else [m["for_whom"]]
            label = f"**{m.get('day')} {m.get('dish')}**"
            allergy_hits, too_long = [], []
            for p in who:
                pref = prefs.get(p, {})
                terms = [t.strip() for t in str(pref.get("allergies") or "").split(",") if t.strip()]
                for hit in foods.allergy_mentions(f"{m.get('dish')} {m.get('ingredients')}", terms):
                    allergy_hits.append(f"*{hit}* ({p})")
                if pref.get("max_prep_minutes") and (m.get("prep_minutes") or 0) > pref["max_prep_minutes"]:
                    too_long.append(f"{p} {pref['max_prep_minutes']} min")
            if allergy_hits:
                flags.append(f"🔎 {label}: the text mentions {', '.join(allergy_hits)}, from an allergy list.")
            if too_long:
                flags.append(f"⏱️ {label} takes {m['prep_minutes']} min, longer than the preferred maximum for "
                             f"{', '.join(too_long)}.")
        if flags:
            with st.container(border=True):
                st.markdown("**Plan notes** (simple text matching on your entries)")
                for f in flags:
                    st.markdown("- " + f)
                st.caption("A missing note does **not** mean a dish is allergy-safe. Always read ingredient labels.")
        if data["meal_plan"]:
            grid = pd.DataFrame(data["meal_plan"])
            grid["entry"] = grid["dish"].fillna("") + grid["for_whom"].map(
                lambda w: "" if w in (None, "", EVERYONE) else f" ({w})")
            pivot = (grid.groupby(["meal", "day"])["entry"].agg(" · ".join).unstack("day")
                     .reindex(columns=storage.DAYS).reindex([m for m in storage.MEALS if m in set(grid["meal"])]))
            st.markdown("**Week at a glance**")
            st.dataframe(pivot.fillna("—"), width="stretch")
        else:
            st.info("No meals planned yet. Click **+** under the table to add one.")

    with fsub[1]:
        g_rows = foods.grocery_list(data["meal_plan"])
        if not g_rows:
            st.info("The grocery list is built from the ingredients in the weekly planner. Add some there first.")
        else:
            gdf = pd.DataFrame(g_rows)
            gdf.insert(0, "Have it", False)
            st.caption("Same item and unit are added together. Items listed in different units are kept "
                       "separate (no guessing conversions). Ticks are for this visit only.")
            st.data_editor(gdf, hide_index=True, width="stretch", key=f"grocery_{ss.ver}", disabled=list(gdf.columns[1:]),
                           column_config={"quantity": num_col("Quantity", fmt="%.2f"), "used_in": "Used in"})
            csv_button(gdf.drop(columns=["Have it"]), "grocery-list.csv")

    with fsub[3]:
        st.markdown("##### Preferences, allergies and restrictions")
        st.caption("Separate allergy words with commas (for example `peanut, sesame`). They are used only to "
                   "point out text matches in the planner.")
        edit_table("food_prefs", {
            "profile": profile_col(), "likes": text_col("Likes"), "allergies": text_col("Allergies"),
            "restrictions": text_col("Dietary restrictions"),
            "max_prep_minutes": num_col("Max prep (min)", 0, 600, 5, "%d"),
        })
        st.markdown("##### Your own nutrition goals (optional)")
        st.caption("Goals are yours to set, ideally with your clinician or dietitian. The app does not suggest "
                   "calorie targets or restrictive diets.")
        edit_table("nutrition_goals", {
            "profile": profile_col(), "kcal": num_col("Calories / day", 0, 10000, 50, "%.0f"),
            "protein_g": num_col("Protein g / day", 0, 500, 1, "%.0f"),
            "fiber_g": num_col("Fiber g / day", 0, 200, 1, "%.0f"), "notes": text_col("Notes"),
        })
        st.markdown("##### My foods (per 100 g)")
        st.caption("Copy values from a package label converted to per 100 g. **Leave a box blank if unknown**: "
                   "blank means 'no data', not zero.")
        edit_table("custom_foods", {
            "name": text_col("Food", required=True), "kcal": num_col("kcal", 0, 900, 1, "%.0f"),
            "protein_g": num_col("Protein g", 0, 100, 0.1, "%.1f"), "carbs_g": num_col("Carbs g", 0, 100, 0.1, "%.1f"),
            "fat_g": num_col("Fat g", 0, 100, 0.1, "%.1f"), "fiber_g": num_col("Fiber g", 0, 100, 0.1, "%.1f"),
            "portion": text_col("Portion name"), "portion_g": num_col("Portion g", 0, 5000, 1, "%.0f"),
            "source_note": text_col("Source"),
        }, profile_filter=False)

    with fsub[4]:
        st.markdown(f"Values per 100 g from [{sources.USDA_FDC['title']}]({sources.USDA_FDC['url']}) "
                    f"(public domain). Look up any row by its FDC ID. Checked {sources.VERIFIED_ON}.")
        fdf = pd.DataFrame(foods.FOODS)[["name", "kcal", "protein_g", "carbs_g", "fat_g", "fiber_g", "portion",
                                        "portion_g", "fdc_id", "fdc_description"]]
        st.dataframe(fdf, hide_index=True, width="stretch", column_config={
            "fdc_id": st.column_config.NumberColumn("FDC ID", format="%d"), "portion_g": "Portion (g)"})
        st.caption("Portion sizes are typical household measures chosen for this app, not USDA values. "
                   "Raw and cooked weights differ; pick the matching row. Real foods vary by brand and recipe.")

# ===========================================================================
# 3. Fitness & Movement
# ===========================================================================

with tab_fit:
    sample_banner()
    st.subheader("🚶 Fitness & Movement")
    st.caption("Log movement, set your own goals and follow simple templates. This is not a rehabilitation "
               "or medical exercise program; if you have a condition or injury, follow your clinician's plan.")
    asub = st.tabs(["📝 Activity log", "🎯 Goals & this week", "📋 Templates"])
    with asub[0]:
        edit_table("activity_log", {
            "date": date_col(required=True), "profile": profile_col(),
            "activity_type": st.column_config.SelectboxColumn("Type", options=storage.ACTIVITY_TYPES, required=True),
            "minutes": num_col("Minutes", 0, 1440, 5, "%.0f"), "steps": num_col("Steps", 0, 100000, 100, "%d"),
            "notes": text_col("Notes"),
        }, defaults={"date": TODAY.isoformat(), "activity_type": "Walking"}, sort_by="date", height=340)
    with asub[1]:
        edit_table("activity_goals", {
            "profile": profile_col(), "weekly_minutes": num_col("Minutes / week", 0, 10080, 10, "%.0f"),
            "strength_sessions": num_col("Strength days / week", 0, 14, 1, "%d"),
            "mobility_sessions": num_col("Mobility days / week", 0, 14, 1, "%d"),
            "daily_steps": num_col("Steps / day", 0, 100000, 500, "%d"),
        })
        with st.expander("📖 Reference: CDC adult activity guideline"):
            st.markdown(f"For adults, CDC says **{sources.ADULT_WEEKLY_MODERATE_MINUTES} minutes of moderate-intensity "
                        f"activity a week** and **at least {sources.ADULT_WEEKLY_STRENGTH_DAYS} days of "
                        f"muscle-strengthening activity**. Source: [{sources.CDC_ACTIVITY_ADULTS['title']}]"
                        f"({sources.CDC_ACTIVITY_ADULTS['url']}), checked {sources.VERIFIED_ON}. Children, pregnancy "
                        "and health conditions have different guidance; your goals are your own.")
        wk_start = insights.week_start(TODAY)
        st.markdown(f"**This week** ({wk_start:%b %d} – {wk_start + timedelta(days=6):%b %d})")
        goal_rows = chosen(data["activity_goals"])
        if not goal_rows:
            st.info("Set a weekly goal above to see progress here.")
        for g in goal_rows:
            wk = insights.activity_week(data, g["profile"], wk_start, TODAY)
            logged = badge(f"{wk['days_logged']} of {wk['days_so_far']} days logged")
            html(f"**{esc(g['profile'])}** {logged}")
            checks = [("Minutes", wk["minutes"], g.get("weekly_minutes")),
                      ("Strength days", wk["strength"], g.get("strength_sessions")),
                      ("Mobility days", wk["mobility"], g.get("mobility_sessions"))]
            for label, val, target in checks:
                if target:
                    st.progress(min(val / target, 1.0), text=f"{label}: {val:.0f} of {target:.0f}"
                                + (" ✅ goal reached" if val >= target else ""))
            if g.get("daily_steps"):
                if wk["steps_days"]:
                    avg = sum(wk["steps_days"]) / len(wk["steps_days"])
                    st.progress(min(avg / g["daily_steps"], 1.0),
                                text=f"Average steps on {len(wk['steps_days'])} day(s) with steps logged: {avg:,.0f} "
                                     f"of {g['daily_steps']:,}")
                else:
                    st.caption("Steps: none logged this week.")
        st.caption("Days without an entry count as *not logged*, not as inactive.")
    with asub[2]:
        st.markdown("Templates are your own plans. **Weekly step** adds a few minutes each week (from the start "
                    "date) until the **cap** you set; use 0 to keep it steady.")
        edit_table("activity_templates", {
            "profile": profile_col(), "name": text_col("Template", required=True),
            "activity_type": st.column_config.SelectboxColumn("Type", options=storage.ACTIVITY_TYPES),
            "days": text_col("Days (e.g. Mon, Wed, Fri)"), "start_date": date_col("Start"),
            "minutes": num_col("Start min", 1, 600, 5, "%.0f"), "weekly_step": num_col("+ min/week", 0, 60, 1, "%.0f"),
            "cap_minutes": num_col("Cap min", 1, 600, 5, "%.0f"), "notes": text_col("Notes"),
        }, defaults={"start_date": TODAY.isoformat(), "weekly_step": 0})
        temps = chosen(valid("activity_templates"))
        if temps:
            ti = st.selectbox("Preview a template", range(len(temps)),
                              format_func=lambda i: f"{temps[i]['profile']}: {temps[i]['name']}")
            t = temps[ti]
            try:
                start = date.fromisoformat(t["start_date"]) if t.get("start_date") else insights.week_start(TODAY)
                plan = calc.progression_plan(t.get("minutes") or 0, t.get("weekly_step") or 0,
                                             t.get("cap_minutes") or t.get("minutes") or 0, weeks=6)
                st.dataframe(pd.DataFrame({
                    "Week starting": [(start + timedelta(weeks=i)).isoformat() for i in range(6)],
                    "Minutes per session": plan, "Days": t.get("days") or "—"}), hide_index=True, width="stretch")
            except ValueError as exc:
                st.error(str(exc))

# ===========================================================================
# 4. Sleep & Wellbeing
# ===========================================================================

with tab_sleep:
    sample_banner()
    st.subheader("🌙 Sleep & Wellbeing")
    st.caption("Log the **date you went to bed**. A wake time earlier than the bedtime means the next morning, "
               "so 23:30 → 06:45 is 7 h 15 min. Ratings are 1 (low) to 5 (high).")
    edit_table("sleep_log", {
        "date": date_col("Night of", required=True), "profile": profile_col(),
        "bedtime": time_col("Bedtime"), "wake_time": time_col("Wake time"),
        "est_sleep_hours": num_col("Est. sleep (h)", 0, 24, 0.25, "%.2f",
                                   help="Optional: your estimate of time actually asleep."),
        "energy": num_col("Energy 1–5", 1, 5, 1, "%d"), "mood": num_col("Mood 1–5", 1, 5, 1, "%d"),
        "stress": num_col("Stress 1–5", 1, 5, 1, "%d"), "notes": text_col("Journal note (optional)"),
    }, defaults={"date": (TODAY - timedelta(days=1)).isoformat()}, sort_by="date", height=340)
    sl = insights.sleep_rows(chosen(valid("sleep_log")))
    if sl:
        recent = sorted(sl, key=lambda r: r["date"], reverse=True)[:14]
        sdf = pd.DataFrame(recent)[["date", "profile", "bedtime", "wake_time", "hours_in_bed", "sleep_hours",
                                    "sleep_basis", "energy", "mood", "stress"]].round(2)
        st.markdown("**Last 14 entries**")
        st.dataframe(sdf, hide_index=True, width="stretch", column_config={
            "hours_in_bed": "Time in bed (h)", "sleep_hours": "Sleep used (h)", "sleep_basis": "Based on"})
    notes = [r for r in sl if r.get("notes")]
    if notes:
        with st.expander(f"📓 Journal notes ({len(notes)})"):
            for r in sorted(notes, key=lambda r: r["date"], reverse=True):
                st.markdown(f"**{fmt_date(r['date'])} · {r['profile']}**: {r['notes']}")
    st.markdown("##### 🛏️ Sleep plan")
    edit_table("sleep_plan", {
        "profile": profile_col(), "target_bedtime": time_col("Target bedtime"), "target_wake": time_col("Target wake"),
    })
    with st.expander("📖 Reference: CDC recommended sleep by age"):
        ref = pd.DataFrame(sources.SLEEP_BY_AGE, columns=["Group", "Age", "From (h)", "To (h)"])
        ref["Hours per day"] = ref.apply(lambda r: f"{r['From (h)']}–{r['To (h)']}" if r["To (h)"] == r["To (h)"]
                                         and r["To (h)"] is not None else f"{r['From (h)']} or more", axis=1)
        st.dataframe(ref[["Group", "Age", "Hours per day"]], hide_index=True, width="stretch")
        st.caption(f"Source: [{sources.CDC_SLEEP['title']}]({sources.CDC_SLEEP['url']}), checked "
                   f"{sources.VERIFIED_ON}. A general reference, not a personal target.")

# ===========================================================================
# 7. Calculators
# ===========================================================================

with tab_calc:
    st.subheader("🧮 Calculators")
    st.caption("Each calculator explains its inputs, formula and limits. None of them diagnoses anything. "
               "There are deliberately no medication, insulin or risk calculators.")
    calc_names = ["⚖️ Adult BMI", "📏 Waist-to-height ratio", "😴 Sleep duration", "🚶 Weekly activity",
                  "🍲 Recipe nutrition per serving", "✅ Habit completion"]
    csub = st.tabs(calc_names)

    with csub[0]:
        system = st.radio("Units", ["Imperial (lb, ft/in)", "Metric (kg, cm)"], horizontal=True, key="bmi_units")
        c1, c2, c3 = st.columns(3)
        if system.startswith("Imperial"):
            w = c1.number_input("Weight (lb)", 0.0, 900.0, 160.0, 0.5)
            ft = c2.number_input("Height (ft)", 0, 8, 5)
            inch = c3.number_input("Height (in)", 0.0, 11.9, 7.0, 0.5)
            kg, cm = calc.lb_to_kg(w), calc.ft_in_to_cm(ft, inch)
        else:
            kg = c1.number_input("Weight (kg)", 0.0, 400.0, 72.0, 0.5)
            cm = c2.number_input("Height (cm)", 0.0, 260.0, 170.0, 0.5)
        a1, a2 = st.columns(2)
        age = a1.number_input("Age (years)", 0, 120, 35, help="Adult categories apply only at 20 and older.")
        preg = a2.checkbox("Currently pregnant", help="Adult BMI categories are not used during pregnancy.")
        try:
            value = calc.bmi(kg, cm)
            st.metric("BMI", f"{value:.1f} kg/m²")
            st.caption(f"Converted: {kg:.1f} kg, {cm:.1f} cm ({calc.kg_to_lb(kg):.1f} lb, {calc.cm_to_in(cm):.1f} in)")
            cat, why = calc.adult_bmi_category(value, age, preg)
            if cat:
                st.info(f"{why} BMI is a screening measure and does not account for muscle, body shape or "
                        f"health history. [Source: CDC]({sources.CDC_ADULT_BMI['url']})")
            else:
                st.warning(why)
                if 2 <= age < 20 and not preg:
                    st.markdown(f"[{sources.CDC_CHILD_BMI['title']}]({sources.CDC_CHILD_BMI['url']})")
        except ValueError as exc:
            st.error(str(exc))
        with st.expander("How it works"):
            st.markdown("**Formula:** BMI = weight (kg) ÷ height (m)². Pounds are converted with 1 kg = 2.20462 lb "
                        "and inches with 1 in = 2.54 cm.\n\n**Categories (adults 20+ only, not in pregnancy):** "
                        + "; ".join(f"{lab} {lo:g}–<{hi:g}" if hi != float("inf") else f"{lab} {lo:g} or more"
                                    for lo, hi, lab in sources.ADULT_BMI_CATEGORIES)
                        + f" ([CDC]({sources.CDC_ADULT_BMI['url']}), checked {sources.VERIFIED_ON}).\n\n"
                        "**Limits:** BMI does not measure body fat directly and is not a diagnosis. Children and "
                        "teens use age- and sex-specific percentiles, which this app does not calculate.")

    with csub[1]:
        unit = st.radio("Unit (both the same)", ["in", "cm"], horizontal=True, key="whtr_unit")
        c1, c2 = st.columns(2)
        waist = c1.number_input(f"Waist ({unit})", 0.0, 300.0, 34.0 if unit == "in" else 86.0, 0.5)
        height = c2.number_input(f"Height ({unit})", 0.0, 300.0, 67.0 if unit == "in" else 170.0, 0.5)
        try:
            st.metric("Waist-to-height ratio", f"{calc.waist_to_height(waist, height):.2f}")
            st.caption("A ratio only. The app does not label it, because a verified reference for every age group "
                       "is outside this app's scope. Discuss it with your clinician if it concerns you.")
        except ValueError as exc:
            st.error(str(exc))
        with st.expander("How it works"):
            st.markdown("**Formula:** waist ÷ height, both in the same unit, so the ratio has no unit.\n\n"
                        "**Measuring:** use a tape at the level your clinician suggests, relaxed, after breathing "
                        "out.\n\n**Limits:** a single measurement can vary by a few centimeters; no interpretation "
                        "is given.")

    with csub[2]:
        c1, c2 = st.columns(2)
        bed = c1.time_input("Bedtime", time(22, 45), step=300, key="calc_bed")
        wake = c2.time_input("Wake time", time(6, 30), step=300, key="calc_wake")
        try:
            h = calc.sleep_hours(bed, wake)
            st.metric("Time in bed", f"{int(h)} h {round((h - int(h)) * 60):02d} min")
            if wake <= bed:
                st.caption("Wake time is at or before bedtime, so it was counted as the next morning.")
        except ValueError as exc:
            st.error(str(exc))
        age_s = st.number_input("Age for the reference (optional)", 0, 120, 0, key="sleep_age",
                                help="Leave at 0 to skip the reference.")
        if age_s:
            ref = calc.sleep_reference(age_s)
            if ref:
                label, lo, hi = ref
                st.caption(f"CDC reference for {label}: {lo}–{hi} hours" if hi else
                           f"CDC reference for {label}: {lo} or more hours")
        with st.expander("How it works"):
            st.markdown("**Formula:** wake time − bedtime. If the wake time is the same as or earlier than the "
                        "bedtime, 24 hours are added (the night crossed midnight).\n\n**Assumption:** this is "
                        "*time in bed*. Time actually asleep is usually shorter.\n\n**Limits:** naps and nights "
                        f"longer than 24 hours are not handled. Reference: [CDC]({sources.CDC_SLEEP['url']}).")

    with csub[3]:
        st.markdown("Enter minutes for each day. **Leave a day blank if not logged**: it is not counted as zero.")
        cols = st.columns(7)
        mins = []
        for i, dname in enumerate(storage.DAYS):
            v = cols[i].number_input(dname, min_value=0, max_value=1440, value=None, step=5, key=f"wk_{dname}")
            mins.append(v)
        goal = st.number_input("Weekly goal (minutes, optional)", min_value=0, max_value=10080, value=150, step=10)
        try:
            res = calc.weekly_activity(mins, goal or None)
            c1, c2 = st.columns(2)
            c1.metric("Total minutes", f"{res['total']:.0f}")
            c2.metric("Days logged", f"{res['days_logged']} of 7")
            if res["progress"] is not None:
                st.progress(min(res["progress"], 1.0), text=f"{res['progress'] * 100:.0f}% of your goal")
        except ValueError as exc:
            st.error(str(exc))
        with st.expander("How it works"):
            st.markdown("**Formula:** total = sum of logged days; progress = total ÷ goal.\n\n**Assumption:** blank "
                        "days are *unknown*, not inactive.\n\n**Limits:** intensity is not considered.")

    with csub[4]:
        st.markdown("Add ingredients with grams and their values **per 100 g** (from labels or Food data). "
                    "Leave unknown values blank.")
        if "recipe_df" not in ss:
            ss.recipe_df = pd.DataFrame([
                {"ingredient": "Lentils, cooked", "grams": 400.0, "kcal": 116.0, "protein_g": 9.02, "carbs_g": 20.1,
                 "fat_g": 0.38, "fiber_g": 7.9},
                {"ingredient": "White rice, cooked", "grams": 300.0, "kcal": 130.0, "protein_g": 2.69,
                 "carbs_g": 28.2, "fat_g": 0.28, "fiber_g": 0.4},
                {"ingredient": "Curry sauce (label had no fiber)", "grams": 200.0, "kcal": 95.0, "protein_g": 1.5,
                 "carbs_g": 8.0, "fat_g": 6.0, "fiber_g": None},
            ])
        add = st.selectbox("Add a food from the dataset", ["—"] + foods.FOOD_NAMES, key="recipe_add")
        if st.button("➕ Add ingredient") and add != "—":
            f = next(x for x in foods.FOODS if x["name"] == add)
            row = {"ingredient": add, "grams": float(f["portion_g"]), **{n: float(f[n]) for n in foods.NUTRIENTS}}
            ss.recipe_df = pd.concat([ss.recipe_df, pd.DataFrame([row])], ignore_index=True)
        recipe = st.data_editor(ss.recipe_df, num_rows="dynamic", hide_index=True, width="stretch", key="recipe_ed",
                                column_config={"grams": num_col("Grams", 0, 10000, 1, "%.0f"),
                                               **{n: num_col(foods.NUTRIENT_LABELS[n] + " /100 g", 0, 900, 0.1, "%.2f")
                                                  for n in foods.NUTRIENTS}})
        servings = st.number_input("Servings", min_value=0.0, max_value=100.0, value=4.0, step=1.0)
        try:
            per = foods.recipe_per_serving(recipe.to_dict("records"), servings)
            cols = st.columns(5)
            for i, n in enumerate(foods.NUTRIENTS):
                v = per[n]["per_serving"]
                cols[i].metric(foods.NUTRIENT_LABELS[n], "—" if v is None else f"{v:.1f}",
                               help=f"{per[n]['missing']} ingredient(s) without data" if per[n]["missing"] else None)
            missing = {foods.NUTRIENT_LABELS[n]: per[n]["missing"] for n in foods.NUTRIENTS if per[n]["missing"]}
            if missing:
                st.warning("Incomplete: " + "; ".join(f"{k} is missing for {v} ingredient(s)" for k, v in missing.items())
                           + ". Those totals are probably underestimates.")
        except ValueError as exc:
            st.error(str(exc))
        with st.expander("How it works"):
            st.markdown("**Formula:** for each ingredient, grams × value per 100 g ÷ 100; add them up; divide by "
                        "servings.\n\n**Assumptions:** values match the state you weighed (raw vs cooked). "
                        "**Limits:** cooking changes water weight; blank values are left out and reported.")

    with csub[5]:
        c1, c2 = st.columns(2)
        done = c1.number_input("Completed check-ins", 0, 1000, 5)
        planned = c2.number_input("Planned check-ins", 0, 1000, 7)
        try:
            pct = calc.completion_percent(done, planned)
            st.metric("Completion", f"{pct:.0f}%")
            st.progress(pct / 100)
        except ValueError as exc:
            st.error(str(exc))
        with st.expander("How it works"):
            st.markdown("**Formula:** completed ÷ planned × 100.\n\n**Limits:** a personal tracking number, not "
                        "a score of health. Unlogged days are better treated as unknown than as missed.")

# ===========================================================================
# 6. Trends
# ===========================================================================

with tab_trends:
    sample_banner()
    st.subheader("📊 Trends")
    st.caption("Only what was logged is drawn. **Gaps mean nothing was logged**, not zero. Markers are individual "
               "entries; dashed lines are averages of logged entries. There is no overall health score.")
    f1, f2, f3 = st.columns([2, 1, 1])
    default_people = names() if ss.get("who", EVERYONE) == EVERYONE else [ss.who]
    people = f1.multiselect("Family members", names(), default=[p for p in default_people if p in names()],
                            key=f"tr_people_{ss.ver}")
    t_start = f2.date_input("From", TODAY - timedelta(days=60), key="tr_from")
    t_end = f3.date_input("To", TODAY, key="tr_to")
    if t_start > t_end:
        st.error("'From' must be on or before 'To'.")
    elif not people:
        st.info("Choose at least one family member.")
    else:
        def pick(key: str, field: str = "date") -> list[dict]:
            return storage.in_date_range(storage.for_profiles(valid(key), people), t_start, t_end, field)

        def source(df: pd.DataFrame, name: str) -> None:
            with st.expander("Source table"):
                if df.empty:
                    st.caption("No rows.")
                else:
                    st.dataframe(df, hide_index=True, width="stretch")
                    csv_button(df, f"{name}-{t_start}-{t_end}.csv")

        excluded = sum(len(data[k]) - len(valid(k)) for k in ("measurements", "activity_log", "sleep_log", "meal_log"))
        if excluded:
            st.warning(f"{excluded} row(s) with problems (impossible values, missing dates, future dates) are "
                       "left out of these charts. Fix them in their tabs.")

        # Weight
        meas = pd.DataFrame(pick("measurements"))
        weights = meas[meas["measure"] == "Weight"].copy() if not meas.empty else pd.DataFrame()
        st.markdown("#### ⚖️ Weight")
        show_avg = st.toggle("Show 28-day average of logged readings", value=False, key="w_avg")
        if not weights.empty:
            weights["date"] = pd.to_datetime(weights["date"])
            weights["entered"] = weights["value"].astype(str) + " " + weights["unit"]
            weights["value"] = [round(weight_to_display(v, u), 1) for v, u in zip(weights["value"], weights["unit"])]
        st.plotly_chart(charts.measurement_chart(weights if not weights.empty else pd.DataFrame(), COLORS,
                                                 f"Weight ({W_UNIT})", W_UNIT, show_avg),
                        config=charts.PLOT_CONFIG, width="stretch")
        st.caption(f"Lines break where readings are more than {charts.MAX_GAP_DAYS} days apart.")
        source(weights[["date", "profile", "value", "entered", "notes"]].rename(columns={"value": W_UNIT})
               if not weights.empty else pd.DataFrame(), "weight")

        # Blood pressure
        st.markdown("#### 🩸 Blood pressure (user-entered)")
        bp = meas[meas["measure"] == "Blood pressure"].copy() if not meas.empty else pd.DataFrame()
        if not bp.empty:
            bp["date"] = pd.to_datetime(bp["date"])
        st.plotly_chart(charts.blood_pressure_chart(bp, COLORS), config=charts.PLOT_CONFIG, width="stretch")
        st.caption("Each reading is drawn as a line from the bottom number to the top number. The app does not "
                   "classify readings; discuss them with your clinician.")
        source(bp[["date", "profile", "value", "value2", "notes"]].rename(
            columns={"value": "systolic", "value2": "diastolic"}) if not bp.empty else pd.DataFrame(), "blood-pressure")

        # Activity
        st.markdown("#### 🚶 Activity minutes and steps")
        act = pd.DataFrame(pick("activity_log"))
        if not act.empty:
            act_daily = charts.daily_series(act, "minutes", t_start, t_end, "sum")
            steps = act.dropna(subset=["steps"]) if "steps" in act else pd.DataFrame()
            steps_daily = charts.daily_series(steps, "steps", t_start, t_end, "sum") if not steps.empty else pd.DataFrame()
        else:
            act_daily = steps_daily = pd.DataFrame()
        st.plotly_chart(charts.daily_bar_chart(act_daily, "minutes", COLORS, "Activity minutes per day", "min")
                        if not act_daily.empty else charts.empty_figure("No activity logged in this range."),
                        config=charts.PLOT_CONFIG, width="stretch")
        st.plotly_chart(charts.daily_line_chart(steps_daily, "steps", COLORS, "Steps per day", "steps", ",.0f")
                        if not steps_daily.empty else charts.empty_figure("No steps logged in this range."),
                        config=charts.PLOT_CONFIG, width="stretch")
        source(act, "activity")

        # Sleep
        st.markdown("#### 🌙 Sleep duration and timing")
        sl_rows = pd.DataFrame(insights.sleep_rows(pick("sleep_log")))
        if not sl_rows.empty:
            sl_daily = charts.daily_series(sl_rows, "sleep_hours", t_start, t_end, "mean")
            st.plotly_chart(charts.daily_line_chart(sl_daily, "sleep_hours", COLORS, "Sleep per night", "h"),
                            config=charts.PLOT_CONFIG, width="stretch")
            sl_rows["date"] = pd.to_datetime(sl_rows["date"])
            st.plotly_chart(charts.sleep_timing_chart(sl_rows, COLORS), config=charts.PLOT_CONFIG, width="stretch")
            st.caption("Sleep per night uses your estimate when given, otherwise time in bed (see 'sleep_basis').")
            sl_rows["date"] = sl_rows["date"].dt.date
        else:
            st.info("No sleep logged in this range.")
        source(sl_rows.drop(columns=["bed_axis", "origin"], errors="ignore").round(2), "sleep")

        # Mood, energy, stress
        st.markdown("#### 🙂 Mood, energy and stress")
        metric = st.radio("Rating", ["mood", "energy", "stress"], horizontal=True, key="tr_metric",
                          format_func=str.capitalize)
        if not sl_rows.empty:
            m_daily = charts.daily_series(sl_rows.assign(date=pd.to_datetime(sl_rows["date"])), metric,
                                          t_start, t_end, "mean")
            fig = charts.daily_line_chart(m_daily, metric, COLORS, f"{metric.capitalize()} rating (1–5)", "/ 5", ".0f")
            fig.update_yaxes(range=[0.5, 5.5], dtick=1)
            st.plotly_chart(fig, config=charts.PLOT_CONFIG, width="stretch")
        else:
            st.info("No ratings logged in this range.")

        # Habits
        st.markdown("#### ✅ Habit completion by week")
        weeks = []
        wk = insights.week_start(t_start)
        while wk <= t_end:
            for h in storage.for_profiles(data["habits"], people):
                hw = insights.habit_week(data, h["profile"], h["habit"], wk, min(TODAY, t_end))
                weeks.append({"week": wk.isoformat(), "label": f"{h['profile']}: {h['habit']}", **hw})
            wk += timedelta(days=7)
        hdf = pd.DataFrame(weeks)
        st.plotly_chart(charts.weekly_percent_chart(hdf, "Done days as % of planned days")
                        if not hdf.empty else charts.empty_figure("No habits for these family members."),
                        config=charts.PLOT_CONFIG, width="stretch")
        source(hdf.round(1) if not hdf.empty else hdf, "habits")

        # Nutrition
        st.markdown("#### 🥗 Meal-log nutrition estimates")
        nutrient = st.radio("Nutrient", foods.NUTRIENTS, horizontal=True, key="tr_nut",
                            format_func=lambda n: foods.NUTRIENT_LABELS[n])
        ml = pick("meal_log")
        if ml:
            items = pd.DataFrame(foods.meal_log_nutrition(ml, data["custom_foods"]))
            agg = []
            for (d_, prof), grp in items.groupby(["date", "profile"]):
                tot = foods.total_nutrition(grp.to_dict("records"))[nutrient]
                agg.append({"date": d_, "profile": prof, nutrient: tot["total"], "missing": tot["missing"]})
            agg_df = pd.DataFrame(agg)
            n_daily = charts.daily_series(agg_df, nutrient, t_start, t_end, "sum")
            miss = charts.daily_series(agg_df, "missing", t_start, t_end, "sum")
            n_daily["missing"] = miss["missing"].values
            st.plotly_chart(charts.nutrition_chart(n_daily, nutrient, COLORS, foods.NUTRIENT_LABELS[nutrient]),
                            config=charts.PLOT_CONFIG, width="stretch")
            st.caption("Hollow markers: some items that day had no data, so the total is incomplete. "
                       "Gaps: no meals logged.")
            source(agg_df.round(1), "nutrition")
        else:
            st.info("No meals logged in this range.")

# ===========================================================================
# 1. Today (rendered last so it reflects every edit made in this run)
# ===========================================================================

with tab_today:
    sample_banner()
    st.subheader(f"🏠 Today · {TODAY:%A, %B} {TODAY.day}")
    who = ss.get("who", EVERYONE)
    people_now = names() if who == EVERYONE else [who]
    if not names():
        st.info("👋 No family members yet. Add one in **📁 Health Records & Care → Profiles**, or load the "
                "sample family at the top of the page.")
    up = reminders.upcoming(data, TODAY, days_ahead=14, profiles=who)
    habits_now = [h for h in storage.for_profiles(data["habits"], who) if h.get("active")]
    today_logs = {(r["profile"], r["habit"]): r.get("done") for r in data["habit_log"] if r.get("date") == TODAY.isoformat()}
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📅 Appointments (14 d)", sum(1 for u in up if u["kind"] == "Appointment"))
    m2.metric("✅ Open care tasks", sum(1 for u in up if u["kind"] == "Care task"))
    m3.metric("🔁 Habits done today", f"{sum(1 for h in habits_now if today_logs.get((h['profile'], h['habit'])))}"
              f" / {len(habits_now)}")
    nights = {r["date"] for r in storage.in_date_range(chosen(data["sleep_log"]), TODAY - timedelta(days=7),
                                                         TODAY - timedelta(days=1))}
    m4.metric("🌙 Nights logged (7 d)", len(nights))

    st.markdown("#### 📌 Priorities")
    st.caption("Chosen by fixed Python rules (listed below), not by AI. Not medical advice.")
    pri = insights.priorities(data, TODAY, profiles=who)
    tones = {"Overdue": ("🔴", "red"), "Soon": ("🟠", "amber"), "Today": ("🔵", "blue"), "This week": ("⚪", "gray")}
    if not pri:
        st.success("Nothing urgent from your records right now.", icon="🌿")
    for p in pri:
        icon, tone = tones[p["level"]]
        level_badge = badge(icon + " " + p["level"], tone)
        html(f"{level_badge} {esc(p['text'])} {origin_badge(p.get('origin'))}")
    with st.expander("How priorities are chosen"):
        for k, v in insights.RULES.items():
            st.markdown(f"- {v}")
        st.markdown("- Order: overdue first, then appointments within 2 days, refills, other items this week, "
                    "habits, sleep logging. At most 6 are shown.")

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### 📅 Coming up (14 days)")
        if not up:
            st.caption("No appointments or confirmed care tasks in the next 14 days.")
        for u in up:
            if u["kind"] not in ("Appointment", "Care task"):
                continue
            when = "Overdue" if u["overdue"] else ("Today" if u["days"] == 0 else fmt_date(u["date"]))
            t = f" {u['time']}" if u.get("time") else ""
            icon = "📅" if u["kind"] == "Appointment" else "✅"
            html(f"{icon} **{esc(when)}{t}** · {esc(u['profile'])}: {esc(u['title'])} {origin_badge(u.get('origin'))}")
    with c2:
        st.markdown("#### 🔁 Habits: check in for today")
        if not habits_now:
            st.caption("No active habits. Add some below.")
        for h in habits_now:
            key = f"hab_{h['profile']}_{h['habit']}_{ss.ver}"
            st.checkbox(f"{h['profile']}: {h['habit']}", value=bool(today_logs.get((h["profile"], h["habit"]))),
                        key=key, on_change=cb_habit, args=(h["profile"], h["habit"], key))
            hw = insights.habit_week(data, h["profile"], h["habit"], insights.week_start(TODAY), TODAY)
            if hw["percent"] is not None:
                st.progress(hw["percent"] / 100, text=f"This week: done on {hw['done']} day(s), plan is {hw['target']}")

    st.markdown("#### 🗓️ Today's plan")
    p1, p2, p3 = st.columns(3)
    day = storage.DAYS[TODAY.weekday()]
    with p1:
        st.markdown("**🥗 Meals**")
        meals = [m for m in data["meal_plan"] if m.get("day") == day
                 and (who == EVERYONE or m.get("for_whom") in (who, EVERYONE, None, ""))]
        if not meals:
            st.caption(f"Nothing planned for {day}. Add meals in 🥗 Nutrition & Meals.")
        for m in sorted(meals, key=lambda m: storage.MEALS.index(m["meal"]) if m.get("meal") in storage.MEALS else 9):
            extra = "" if m.get("for_whom") in (None, "", EVERYONE) else f" ({m['for_whom']})"
            prep = f" · {m['prep_minutes']} min" if m.get("prep_minutes") else ""
            html(f"{esc(m.get('meal') or 'Meal')}: **{esc(m['dish'])}**{esc(extra)}<small>{prep}</small> "
                 f"{origin_badge(m.get('origin'))}")
    with p2:
        st.markdown("**🚶 Movement**")
        todays = [t for t in storage.for_profiles(valid("activity_templates"), who)
                  if day in storage.parse_days(t.get("days"))]
        if not todays:
            st.caption("No templates scheduled today.")
        for t in todays:
            start = date.fromisoformat(t["start_date"]) if t.get("start_date") else None
            mins = calc.template_minutes(t.get("minutes") or 0, t.get("weekly_step") or 0, t.get("cap_minutes"),
                                         start, TODAY)
            html(f"{esc(t['profile'])}: **{esc(t['name'])}**, {mins:.0f} min {origin_badge(t.get('origin'))}")
    with p3:
        st.markdown("**🌙 Sleep plan**")
        plans = storage.for_profiles(data["sleep_plan"], who)
        if not plans:
            st.caption("No sleep plan yet. Add one in 🌙 Sleep & Wellbeing.")
        for sp in plans:
            if sp.get("target_bedtime") and sp.get("target_wake"):
                hrs = calc.sleep_hours(sp["target_bedtime"], sp["target_wake"])
                html(f"{esc(sp['profile'])}: bed **{sp['target_bedtime']}**, up **{sp['target_wake']}** "
                     f"<small>({hrs:.1f} h in bed)</small> {origin_badge(sp.get('origin'))}")

    st.markdown("#### 🔎 Rule-based observations")
    st.caption("Plain comparisons of what was logged, not AI and not medical advice. They describe entries; "
               "they do not explain causes or name conditions.")
    if people_now:
        target = st.selectbox("For", people_now, key="obs_for") if len(people_now) > 1 else people_now[0]
        for o in insights.observations(data, target, TODAY):
            (st.caption if o["kind"] == "note" else st.markdown)(("ℹ️ " if o["kind"] == "note" else "• ") + o["text"])

    with st.expander("✏️ Edit habits and past check-ins"):
        edit_table("habits", {
            "profile": profile_col(), "habit": text_col("Habit", required=True),
            "days_per_week": num_col("Planned days / week", 1, 7, 1, "%d"), "active": check_col("Active", default=True),
        }, defaults={"days_per_week": 7, "active": True})
        edit_table("habit_log", {
            "date": date_col(required=True), "profile": profile_col(), "habit": text_col("Habit"),
            "done": check_col("Done"),
        }, sort_by="date", height=260)
        if data["habits"] != ss.base["habits"] or data["habit_log"] != ss.base["habit_log"]:
            commit()  # Today was drawn before these editors; redraw so it shows the change
            st.rerun()

st.divider()
st.caption("Family Health & Wellness Copilot · an organizer, not a medical device · rule-based, no AI · "
           "data stays in this browser session · sources: CDC, USDA FoodData Central (see each tab)")
