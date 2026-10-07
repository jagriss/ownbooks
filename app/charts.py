"""Altair chart builders, themed to the reference data-viz palette.

Description: One accent hue (blue) for the series of interest and a
    gray for context -- these charts are single-series or "emphasis"
    (one category highlighted against the total), never categorical, so
    no multi-hue palette is needed. Light and dark use their own
    validated steps, picked from the viewer's Streamlit theme.
Usage: imported by app/views/*.py.
"""

import altair as alt
import pandas as pd
import streamlit as st

PALETTE = {
    "light": {
        "accent": "#2a78d6",
        "context": "#c3c2b7",
        "ink": "#0b0b0b",
        "muted": "#898781",
        "grid": "#e1e0d9",
        "baseline": "#c3c2b7",
    },
    "dark": {
        "accent": "#3987e5",
        "context": "#52514e",
        "ink": "#ffffff",
        "muted": "#898781",
        "grid": "#2c2c2a",
        "baseline": "#383835",
    },
}


def colors() -> dict[str, str]:
    mode = getattr(st.context.theme, "type", None) or "light"
    return PALETTE["dark" if mode == "dark" else "light"]


def _configure(chart: alt.Chart, height: int) -> alt.Chart:
    c = colors()
    return (
        chart.properties(height=height)
        .configure(background="transparent")
        .configure_view(stroke=None)
        .configure_axis(
            labelColor=c["muted"],
            titleColor=c["muted"],
            gridColor=c["grid"],
            gridWidth=1,
            domainColor=c["baseline"],
            tickColor=c["baseline"],
            labelFontSize=12,
            titleFontSize=12,
            titleFontWeight="normal",
        )
        .configure_axisX(grid=False)
    )


def monthly_spend(df: pd.DataFrame, highlight: str | None) -> alt.Chart:
    """Monthly spend bars; with `highlight`, that category in the accent
    over the gray monthly total (emphasis form)."""
    c = colors()
    totals = (
        df.groupby("txn_month", as_index=False)
        .agg(spend=("spend", "sum"), txn_count=("txn_count", "sum"))
        .assign(series="All spend")
    )
    x = alt.X(
        "yearmonth(txn_month):O",
        title=None,
        axis=alt.Axis(format="%b %y", labelAngle=0),
    )
    y = alt.Y("spend:Q", title=None, axis=alt.Axis(format="$,.0f", tickCount=5))
    hover = alt.selection_point(
        on="pointerover", fields=["txn_month"], empty=False, clear="pointerout"
    )
    tooltip = [
        alt.Tooltip("yearmonth(txn_month):T", title="Month", format="%B %Y"),
        alt.Tooltip("series:N", title="Series"),
        alt.Tooltip("spend:Q", title="Spend", format="$,.2f"),
        alt.Tooltip("txn_count:Q", title="Transactions"),
    ]
    bar = dict(
        width={"band": 0.62}, cornerRadiusTopLeft=4, cornerRadiusTopRight=4
    )

    base = (
        alt.Chart(totals)
        .mark_bar(**bar)
        .encode(
            x=x,
            y=y,
            color=alt.value(c["context"] if highlight else c["accent"]),
            opacity=alt.condition(hover, alt.value(1), alt.value(0.88)),
            tooltip=tooltip,
        )
        .add_params(hover)
    )
    if not highlight:
        return _configure(base, 280)

    focus = (
        df[df["category"] == highlight]
        .groupby("txn_month", as_index=False)
        .agg(spend=("spend", "sum"), txn_count=("txn_count", "sum"))
        .assign(series=highlight)
    )
    front = (
        alt.Chart(focus)
        .mark_bar(**bar)
        .encode(x=x, y=y, color=alt.value(c["accent"]), tooltip=tooltip)
    )
    return _configure(alt.layer(base, front), 280)


def category_bars(df: pd.DataFrame) -> alt.Chart:
    """Horizontal ranked bars of spend by category, one hue."""
    c = colors()
    data = df[df["spend"] > 0].sort_values("spend", ascending=False)
    hover = alt.selection_point(
        on="pointerover", fields=["category"], empty=False, clear="pointerout"
    )
    chart = (
        alt.Chart(data)
        .mark_bar(
            height={"band": 0.62},
            cornerRadiusTopRight=4,
            cornerRadiusBottomRight=4,
        )
        .encode(
            y=alt.Y(
                "category:N",
                sort="-x",
                title=None,
                axis=alt.Axis(labelColor=c["ink"], labelLimit=160),
            ),
            x=alt.X(
                "spend:Q",
                title=None,
                axis=alt.Axis(format="$~s", tickCount=4, labelFlush=True),
            ),
            color=alt.value(c["accent"]),
            opacity=alt.condition(hover, alt.value(1), alt.value(0.88)),
            tooltip=[
                alt.Tooltip("category:N", title="Category"),
                alt.Tooltip("category_group:N", title="Group"),
                alt.Tooltip("spend:Q", title="Spend", format="$,.2f"),
                alt.Tooltip("share:Q", title="Share", format=".1%"),
                alt.Tooltip("txn_count:Q", title="Transactions"),
            ],
        )
        .add_params(hover)
    )
    return _configure(chart, max(160, 28 * len(data)))
