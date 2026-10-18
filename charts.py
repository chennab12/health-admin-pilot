"""Plotly charts for the Trends tab.

Rules every chart follows:
- Only logged values are plotted. Nothing is filled in or interpolated.
- Daily series are put on a full calendar so unlogged days show as gaps.
- Sparse measurements (like weight) break the line when readings are more
  than MAX_GAP_DAYS apart.
- Rolling averages are drawn as a separate dashed line, computed from logged
  readings only, and labelled as averages.
- Each family member keeps the same colour in every chart.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import plotly.graph_objects as go

import calculations as calc

# Categorical palette in fixed order (validated for colour-vision deficiency).
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#e87ba4", "#6250d6", "#eda100", "#008300", "#e34948"]
NEUTRAL = "#8a8f98"
PLOT_CONFIG = {"displayModeBar": False, "responsive": True}
MAX_GAP_DAYS = 14


def profile_colors(names: list[str]) -> dict[str, str]:
    """Colour follows the family member, by their position in the profile list."""
    return {n: SERIES[i % len(SERIES)] for i, n in enumerate(names)}


def style(fig: go.Figure, title: str, y_title: str = "", height: int = 340) -> go.Figure:
    fig.update_layout(
        title=dict(text=title, x=0, xanchor="left", font=dict(size=15)), height=height,
        margin=dict(l=8, r=8, t=70, b=8), hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, x=0, xanchor="left", title_text=""),
        bargap=0.25, bargroupgap=0.08,
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(title_text=y_title, gridcolor="rgba(128,128,128,0.18)", zeroline=False)
    return fig


def empty_figure(message: str) -> go.Figure:
    fig = go.Figure()
    fig.add_annotation(text=message, x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    fig.update_layout(height=160, margin=dict(l=8, r=8, t=8, b=8))
    return fig


# ---------------------------------------------------------------------------
# Data shaping
# ---------------------------------------------------------------------------

def daily_series(df: pd.DataFrame, value: str, start: date, end: date, how: str = "sum") -> pd.DataFrame:
    """One row per calendar day per profile. Days with no logged value are NaN (a gap), not 0."""
    days = pd.date_range(start, end, freq="D")
    frames = []
    for name, grp in df.groupby("profile"):
        grp = grp.dropna(subset=[value])
        per_day = grp.groupby(pd.to_datetime(grp["date"]))[value].agg(how)
        full = per_day.reindex(days)
        frames.append(pd.DataFrame({"date": days, "profile": name, value: full.values}))
    if not frames:
        return pd.DataFrame(columns=["date", "profile", value])
    return pd.concat(frames, ignore_index=True)


def break_long_gaps(df: pd.DataFrame, value_cols: list[str], max_gap_days: int = MAX_GAP_DAYS) -> pd.DataFrame:
    """Insert an empty row between readings more than max_gap_days apart so the line breaks there."""
    out = []
    df = df.sort_values("date")
    prev = None
    for _, row in df.iterrows():
        if prev is not None and (row["date"] - prev).days > max_gap_days:
            gap = {c: None for c in df.columns}
            gap["date"] = prev + (row["date"] - prev) / 2
            gap["profile"] = row["profile"]
            out.append(gap)
        out.append(row.to_dict())
        prev = row["date"]
    res = pd.DataFrame(out, columns=df.columns)
    for c in value_cols:
        res[c] = pd.to_numeric(res[c], errors="coerce")
    return res


def rolling_average(df: pd.DataFrame, value: str, days: int = 7, min_periods: int = 2) -> pd.DataFrame:
    """Time-based rolling mean of logged readings only (no filling). Needs min_periods readings in the window."""
    df = df.dropna(subset=[value]).sort_values("date").set_index("date")
    roll = df[value].rolling(f"{days}D", min_periods=min_periods).mean()
    return roll.reset_index().rename(columns={value: "avg"})


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def measurement_chart(df: pd.DataFrame, colors: dict, title: str, unit: str, show_avg: bool) -> go.Figure:
    """Individual readings as markers + line (broken at long gaps); optional rolling average dashed."""
    if df.empty:
        return empty_figure("No readings in this range.")
    fig = go.Figure()
    for name, grp in df.groupby("profile", sort=False):
        grp = break_long_gaps(grp[["date", "profile", "value"]], ["value"])
        fig.add_trace(go.Scatter(x=grp["date"], y=grp["value"], mode="lines+markers", name=f"{name} (readings)",
                                 line=dict(color=colors.get(name, NEUTRAL), width=2), marker=dict(size=8),
                                 connectgaps=False, hovertemplate=f"%{{y:.1f}} {unit}<extra>{name}</extra>"))
        if show_avg:
            avg = rolling_average(df[df["profile"] == name], "value", days=28, min_periods=2)
            fig.add_trace(go.Scatter(x=avg["date"], y=avg["avg"], mode="lines", name=f"{name} (28-day average)",
                                     line=dict(color=colors.get(name, NEUTRAL), width=2, dash="dash"),
                                     hovertemplate=f"avg %{{y:.1f}} {unit}<extra>{name}</extra>"))
    return style(fig, title, unit)


def blood_pressure_chart(df: pd.DataFrame, colors: dict) -> go.Figure:
    """Each reading drawn as a vertical line from diastolic (bottom) to systolic (top). No categories shown."""
    if df.empty:
        return empty_figure("No blood pressure readings in this range.")
    fig = go.Figure()
    for name, grp in df.groupby("profile", sort=False):
        c = colors.get(name, NEUTRAL)
        xs, ys = [], []
        for _, r in grp.iterrows():
            xs += [r["date"], r["date"], None]
            ys += [r["value2"], r["value"], None]
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", line=dict(color=c, width=2), showlegend=False,
                                 hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=grp["date"], y=grp["value"], mode="markers", name=f"{name} systolic (top)",
                                 marker=dict(color=c, size=9, symbol="triangle-up"),
                                 hovertemplate="Systolic %{y:.0f} mmHg<extra>" + name + "</extra>"))
        fig.add_trace(go.Scatter(x=grp["date"], y=grp["value2"], mode="markers", name=f"{name} diastolic (bottom)",
                                 marker=dict(color=c, size=9, symbol="triangle-down"),
                                 hovertemplate="Diastolic %{y:.0f} mmHg<extra>" + name + "</extra>"))
    fig = style(fig, "Blood pressure readings (as entered)", "mmHg")
    fig.update_layout(hovermode="closest")
    return fig


def daily_bar_chart(daily: pd.DataFrame, value: str, colors: dict, title: str, y_title: str) -> go.Figure:
    if daily.empty or daily[value].dropna().empty:
        return empty_figure("Nothing logged in this range.")
    fig = go.Figure()
    for name, grp in daily.groupby("profile", sort=False):
        fig.add_trace(go.Bar(x=grp["date"], y=grp[value], name=name, marker_color=colors.get(name, NEUTRAL),
                             marker_cornerradius=4, hovertemplate=f"%{{y:,.0f}} {y_title}<extra>{name}</extra>"))
    return style(fig, title, y_title)


def daily_line_chart(daily: pd.DataFrame, value: str, colors: dict, title: str, y_title: str,
                     fmt: str = ".1f") -> go.Figure:
    if daily.empty or daily[value].dropna().empty:
        return empty_figure("Nothing logged in this range.")
    fig = go.Figure()
    for name, grp in daily.groupby("profile", sort=False):
        fig.add_trace(go.Scatter(x=grp["date"], y=grp[value], name=name, mode="lines+markers", connectgaps=False,
                                 line=dict(color=colors.get(name, NEUTRAL), width=2), marker=dict(size=7),
                                 hovertemplate=f"%{{y:{fmt}}} {y_title}<extra>{name}</extra>"))
    return style(fig, title, y_title)


def sleep_timing_chart(rows: pd.DataFrame, colors: dict) -> go.Figure:
    """Floating bars from bedtime to wake time on an evening-centred clock axis."""
    rows = rows.dropna(subset=["bed_axis", "hours_in_bed"])
    if rows.empty:
        return empty_figure("No nights with both bedtime and wake time in this range.")
    fig = go.Figure()
    for name, grp in rows.groupby("profile", sort=False):
        fig.add_trace(go.Bar(
            x=grp["date"], y=grp["hours_in_bed"], base=grp["bed_axis"], name=name,
            marker_color=colors.get(name, NEUTRAL), marker_cornerradius=4,
            customdata=list(zip(grp["bedtime"], grp["wake_time"], grp["hours_in_bed"])),
            hovertemplate="Bed %{customdata[0]} → up %{customdata[1]} (%{customdata[2]:.1f} h in bed)"
                          "<extra>" + name + "</extra>"))
    low = int(rows["bed_axis"].min()) - 1
    high = int((rows["bed_axis"] + rows["hours_in_bed"]).max()) + 1
    ticks = list(range(low, high + 1, 2))
    fig = style(fig, "Sleep timing: bedtime to wake time", "Clock time", height=380)
    fig.update_yaxes(tickvals=ticks, ticktext=[calc.clock_label(t) for t in ticks], autorange="reversed")
    fig.update_layout(barmode="group", hovermode="closest")
    return fig


def weekly_percent_chart(df: pd.DataFrame, title: str) -> go.Figure:
    """Habit completion % per week; weeks with no check-ins have no bar."""
    if df.empty or df["percent"].dropna().empty:
        return empty_figure("No habit check-ins in this range.")
    fig = go.Figure()
    for i, (label, grp) in enumerate(df.groupby("label", sort=False)):
        fig.add_trace(go.Bar(x=grp["week"], y=grp["percent"], name=label, marker_color=SERIES[i % len(SERIES)],
                             marker_cornerradius=4, customdata=list(zip(grp["done"], grp["target"], grp["not_logged"])),
                             hovertemplate="%{y:.0f}% (done %{customdata[0]} of %{customdata[1]} planned; "
                                           "%{customdata[2]} day(s) not logged)<extra>" + label + "</extra>"))
    fig = style(fig, title, "% of planned days")
    fig.update_yaxes(range=[0, 105], ticksuffix="%")
    fig.update_layout(hovermode="closest")
    return fig


def nutrition_chart(daily: pd.DataFrame, value: str, colors: dict, label: str) -> go.Figure:
    """Daily estimated totals for logged days. Hollow markers = some items on that day had no data."""
    if daily.empty or daily[value].dropna().empty:
        return empty_figure("No meals with nutrition data logged in this range.")
    fig = go.Figure()
    for name, grp in daily.groupby("profile", sort=False):
        c = colors.get(name, NEUTRAL)
        partial = grp["missing"].fillna(0) > 0
        fig.add_trace(go.Scatter(
            x=grp["date"], y=grp[value], name=name, mode="lines+markers", connectgaps=False,
            line=dict(color=c, width=2),
            marker=dict(size=9, color=["white" if p else c for p in partial], line=dict(color=c, width=2)),
            customdata=grp["missing"].fillna(0),
            hovertemplate="%{y:,.0f} (estimate; %{customdata:.0f} item(s) without data)<extra>" + name + "</extra>"))
    return style(fig, f"Estimated {label} per logged day", label)
