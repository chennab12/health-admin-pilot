"""In-app reminders and calendar (.ics) files.

Reminders are shown only while the app is open. The .ics file lets people put
dates into their own calendar app, which is what can actually alert them.
"""

from __future__ import annotations

import hashlib
from datetime import date, datetime, timedelta, timezone

import storage


def upcoming(data: dict, today: date, days_ahead: int = 14, profiles=None) -> list[dict]:
    """Dated items (appointments, care tasks, refills, vaccinations due) from overdue up to days_ahead.

    Only real, open items: done tasks, unconfirmed tasks and inactive medications are left out.
    """
    end = (today + timedelta(days=days_ahead)).isoformat()
    items = []
    for a in storage.for_profiles(data.get("appointments", []), profiles):
        if a.get("date") and today.isoformat() <= a["date"] <= end:
            items.append({"date": a["date"], "time": a.get("time"), "profile": a["profile"], "kind": "Appointment",
                          "title": f"{a.get('purpose') or 'Appointment'} with {a.get('with_whom') or 'clinician'}",
                          "origin": a.get("origin")})
    for t in storage.for_profiles(data.get("care_tasks", []), profiles):
        if t.get("due_date") and t.get("confirmed") and not t.get("done") and t["due_date"] <= end:
            items.append({"date": t["due_date"], "time": None, "profile": t["profile"], "kind": "Care task",
                          "title": t.get("task") or "Care task", "origin": t.get("origin")})
    for m in storage.for_profiles(data.get("medications", []), profiles):
        if m.get("refill_date") and m.get("active") and m["refill_date"] <= end:
            items.append({"date": m["refill_date"], "time": None, "profile": m["profile"], "kind": "Refill",
                          "title": f"Refill: {m.get('medication')}", "origin": m.get("origin")})
    for v in storage.for_profiles(data.get("vaccinations", []), profiles):
        if v.get("next_due") and v["next_due"] <= end:
            items.append({"date": v["next_due"], "time": None, "profile": v["profile"], "kind": "Vaccination due",
                          "title": f"{v.get('vaccine')} {v.get('dose_note') or ''} (date you recorded)".replace("  ", " "),
                          "origin": v.get("origin")})
    for it in items:
        it["overdue"] = it["date"] < today.isoformat()
        it["days"] = (date.fromisoformat(it["date"]) - today).days
    return sorted(items, key=lambda r: (r["date"], r.get("time") or ""))


def _escape(text: str) -> str:
    return (str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))


def _fold(line: str) -> list[str]:
    """RFC 5545 lines are at most 75 octets; longer lines continue with a leading space."""
    out, raw = [], line.encode("utf-8")
    while len(raw) > 75:
        cut = 75 if not out else 74
        while cut > 0 and (raw[cut] & 0xC0) == 0x80:  # do not split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = raw[cut:]
    out.append(raw.decode("utf-8"))
    return [out[0]] + [" " + part for part in out[1:]]


def to_ics(items: list[dict], private_titles: bool = False, now: datetime | None = None) -> str:
    """Build an .ics calendar. Timed items last 1 hour; items without a time are all-day.

    private_titles=True writes 'Health reminder' instead of names and details.
    """
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Family Health & Wellness Copilot//EN", "CALSCALE:GREGORIAN"]
    for it in items:
        day = date.fromisoformat(it["date"])
        title = "Health reminder" if private_titles else f"{it['kind']}: {it['title']} ({it['profile']})"
        uid = hashlib.sha1(f"{it['date']}|{it.get('time')}|{it['kind']}|{it['title']}|{it['profile']}"
                           .encode()).hexdigest()[:20]
        lines += ["BEGIN:VEVENT", f"UID:{uid}@family-health-copilot", f"DTSTAMP:{stamp}"]
        if it.get("time"):
            hh, mm = it["time"].split(":")
            start = datetime(day.year, day.month, day.day, int(hh), int(mm))
            end = start + timedelta(hours=1)
            lines += [f"DTSTART:{start:%Y%m%dT%H%M%S}", f"DTEND:{end:%Y%m%dT%H%M%S}"]
        else:
            lines += [f"DTSTART;VALUE=DATE:{day:%Y%m%d}", f"DTEND;VALUE=DATE:{day + timedelta(days=1):%Y%m%d}"]
        lines += _fold(f"SUMMARY:{_escape(title)}")
        if not private_titles:
            lines += _fold(f"DESCRIPTION:{_escape('Added from Family Health & Wellness Copilot. Check details with your clinic.')}")
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", "DESCRIPTION:Reminder", "TRIGGER:-PT12H" if it.get("time")
                  else "TRIGGER:PT9H", "END:VALARM", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


APPOINTMENT_PREP = [
    "Write down the main reason for the visit in one or two sentences.",
    "Note when symptoms or changes started and what you have noticed since.",
    "Bring the list of current medications from the Records tab (names and schedules as prescribed).",
    "Bring any home readings you were asked to keep (export the table as CSV or print it).",
    "Check insurance card, ID and any referral or forms the clinic asked for.",
    "Write your questions below, most important first.",
    "Ask the clinician to repeat or write down any new instructions, then record them here.",
]
