"""Streamlit front end for the finance warehouse.

Description: Entry point. Sets up navigation, the sidebar period
    filter, and the new-statements banner shown on every page; each
    page lives in app/views/. All data changes go through
    ingest/refresh.py (build on a copy, swap in if tests pass).
Usage: pixi run app   (serves on http://localhost:8501, this machine only)
"""

from datetime import date

import streamlit as st
from dateutil.relativedelta import relativedelta

import data

st.set_page_config(
    page_title="ownbooks", page_icon=":material/savings:", layout="wide"
)

PERIODS = {
    "Last 3 months": 3,
    "Last 6 months": 6,
    "Last 12 months": 12,
    "Year to date": "ytd",
    "All time": None,
}


def _sidebar() -> None:
    """Period filter (shared via session_state) and pipeline actions."""
    if data.db_exists():
        bounds = data.query(
            f"""
            SELECT
            min(txn_date) AS lo
            ,max(txn_date) AS hi
            FROM {data.CATALOG}.main_marts.fct_transactions
            """
        ).iloc[0]
        lo, hi = bounds["lo"].date(), bounds["hi"].date()
        choice = st.sidebar.selectbox("Period", list(PERIODS), index=2)
        months = PERIODS[choice]
        # Periods are whole months ending with the latest month of data.
        end = hi
        if months == "ytd":
            start = date(hi.year, 1, 1)
        elif months is None:
            start = lo
        else:
            start = date(hi.year, hi.month, 1) - relativedelta(
                months=months - 1
            )
        st.session_state["period"] = (max(start, lo), end)
        st.sidebar.caption(f"{start:%b %d, %Y} – {end:%b %d, %Y}")

    st.sidebar.divider()
    if st.sidebar.button(
        "Refresh everything",
        icon=":material/refresh:",
        width="stretch",
        help="Reload every statement and rebuild all models. New files "
        "are picked up automatically; use this after editing seeds by hand.",
    ):
        data.refresh_with_status(ingest=True, success="Refreshed")


def _new_statements_banner() -> None:
    """Offer to load statement files the warehouse hasn't seen yet."""
    new = data.new_statements()
    if not new:
        return
    with st.container(border=True):
        text, button = st.columns([4, 1], vertical_alignment="center")
        listing = ", ".join(f"`{p}`" for p in new[:3])
        more = f" and {len(new) - 3} more" if len(new) > 3 else ""
        text.markdown(
            f":material/upload_file: **{len(new)} new statement "
            f"file{'s' if len(new) != 1 else ''}**: {listing}{more}"
        )
        if button.button("Load", type="primary", width="stretch"):
            data.refresh_with_status(
                ingest=True, success=f"Loaded {len(new)} file(s)"
            )


pages = [
    st.Page(
        "views/overview.py",
        title="Overview",
        icon=":material/bar_chart:",
        default=True,
    ),
    st.Page(
        "views/transactions.py",
        title="Transactions",
        icon=":material/receipt_long:",
    ),
    st.Page(
        "views/subscriptions.py",
        title="Subscriptions",
        icon=":material/autorenew:",
    ),
    st.Page("views/categorize.py", title="Categorize", icon=":material/sell:"),
    st.Page("views/sql.py", title="SQL", icon=":material/terminal:"),
]
nav = st.navigation(pages)
_sidebar()
if flash := st.session_state.pop("flash", None):
    st.toast(flash, icon=":material/check_circle:")
_new_statements_banner()

if not data.db_exists():
    st.title("No data yet")
    st.write(
        "Put Chase/Amex CSV exports in `data/statements/<account_key>/` "
        "and they'll show up above, ready to load. To try it out first, "
        "run `pixi run dummy-data`."
    )
    st.stop()

nav.run()
