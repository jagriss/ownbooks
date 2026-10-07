"""Subscriptions: recurring charges, upcoming renewals, annual cost."""

from datetime import date, timedelta

import streamlit as st

import data

st.title("Subscriptions")
st.caption(
    "Merchants charging a near-constant amount (±5%) every 25–35 days, "
    "3+ times. Detected automatically from all history, categorized or not."
)

subs = data.query(
    "FROM main_marts.mart_subscriptions ORDER BY annualized_cost DESC"
)
if subs.empty:
    st.info("No recurring charges detected yet; it needs 3+ months of data.")
    st.stop()

today = date.today()
subs["next_expected"] = subs["next_expected"].dt.date
subs["days_until"] = subs["next_expected"].map(lambda d: (d - today).days)
soon = subs[subs["days_until"].between(0, 7)]
lapsed = subs[subs["days_until"] < -10]

m1, m2, m3 = st.columns(3, border=True)
m1.metric("Recurring charges", len(subs))
m2.metric("Per month", f"${subs['avg_amount'].sum():,.2f}")
m3.metric("Per year", f"${subs['annualized_cost'].sum():,.0f}")

if not soon.empty:
    names = ", ".join(
        f"**{data.md(r.merchant_name)}** ({data.md(f'${r.avg_amount:,.2f}')}, {r.next_expected:%b %d})"
        for r in soon.itertuples()
    )
    st.warning(
        f"Due in the next 7 days: {names}", icon=":material/event_upcoming:"
    )
if not lapsed.empty:
    names = ", ".join(f"**{data.md(n)}**" for n in lapsed["merchant_name"])
    st.info(
        f"Overdue by 10+ days, possibly cancelled (or your statements are older than today): {names}",
        icon=":material/event_busy:",
    )

st.dataframe(
    subs[
        [
            "merchant_name",
            "category",
            "avg_amount",
            "annualized_cost",
            "charge_count",
            "first_charged",
            "last_charged",
            "next_expected",
            "days_until",
        ]
    ],
    hide_index=True,
    width="stretch",
    column_config={
        "merchant_name": "Merchant",
        "category": "Category",
        "avg_amount": st.column_config.NumberColumn("Monthly", format="dollar"),
        "annualized_cost": st.column_config.ProgressColumn(
            "Per year",
            format="dollar",
            min_value=0,
            max_value=float(subs["annualized_cost"].max()),
        ),
        "charge_count": "Charges",
        "first_charged": st.column_config.DateColumn(
            "Since", format="MMM YYYY"
        ),
        "last_charged": st.column_config.DateColumn("Last", format="MMM D"),
        "next_expected": st.column_config.DateColumn("Next", format="MMM D"),
        "days_until": st.column_config.NumberColumn(
            "Days until", help="Negative = overdue"
        ),
    },
)
