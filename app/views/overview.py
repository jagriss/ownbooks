"""Overview: headline numbers, monthly spend, and spend by category."""

import streamlit as st

import charts
import data

start, end = st.session_state["period"]
st.title("Overview")

monthly = data.query(
    """
    SELECT txn_month, category_group, category, txn_count, spend
    FROM main_marts.mart_monthly_spend
    WHERE txn_month BETWEEN date_trunc('month', ?::date) AND ?
    """,
    (start, end),
)
flows = data.query(
    """
    SELECT
        sum(spend_amount) FILTER (WHERE is_spend) AS spend,
        sum(amount) FILTER (WHERE category = 'Income') AS income,
        count(DISTINCT txn_month) AS months
    FROM main_marts.fct_transactions
    WHERE txn_date BETWEEN ? AND ?
    """,
    (start, end),
).iloc[0]
subs = data.query(
    "SELECT sum(annualized_cost) AS annual FROM main_marts.mart_subscriptions"
).iloc[0]
uncategorized = data.query(
    """
    SELECT count(*) AS n, coalesce(sum(spend_amount), 0) AS spend
    FROM main_marts.fct_transactions
    WHERE category = 'Uncategorized' AND txn_date BETWEEN ? AND ?
    """,
    (start, end),
).iloc[0]

# --- KPI row ----------------------------------------------------------------
spend = float(flows["spend"] or 0)
income = float(flows["income"] or 0)
months = max(int(flows["months"] or 1), 1)
by_month = monthly.groupby("txn_month")["spend"].sum().sort_index()
latest, prior = (
    (by_month.iloc[-1], by_month.iloc[:-1].tail(3).mean())
    if len(by_month) > 1
    else (spend, None)
)

# 2x2 so values never truncate, whatever the window width.
row1, row2 = st.columns(2), st.columns(2)
k1, k2, k3, k4 = (col.container(border=True) for col in (*row1, *row2))
k1.metric(
    "Spent",
    f"${spend:,.0f}",
    help="Net of refunds; excludes transfers and income.",
    chart_data=by_month.round(2).tolist(),
    chart_type="bar",
)
k2.metric(
    "Latest month",
    f"${latest:,.0f}",
    delta=(
        None
        if prior is None
        else f"{(latest - prior) / prior:+.0%} vs prior 3-mo avg"
    ),
    delta_color="inverse",
)
k3.metric(
    "Saved",
    f"${income - spend:,.0f}",
    delta=f"{(income - spend) / income:.0%} of income" if income else None,
    delta_color="off",
    delta_arrow="off",
)
k4.metric("Subscriptions / yr", f"${float(subs['annual'] or 0):,.0f}")

if uncategorized["n"]:
    st.info(
        f"**{int(uncategorized['n'])} transactions "
        f"({data.md(f'${float(uncategorized['spend']):,.0f}')})** "
        "in this period are uncategorized.",
        icon=":material/sell:",
    )
    st.page_link(
        "views/categorize.py",
        label="Categorize them",
        icon=":material/arrow_forward:",
    )

# --- Monthly spend ----------------------------------------------------------
left, right = st.columns([3, 2], gap="large")
with left:
    st.subheader("Spend by month")
    options = sorted(monthly["category"].unique())
    highlight = st.selectbox("Highlight a category", ["None", *options])
    highlight = None if highlight == "None" else highlight
    if highlight:
        st.caption(
            f"**{data.md(highlight)}** in blue against total spend in gray"
        )
    st.altair_chart(
        charts.monthly_spend(monthly, highlight), width="stretch", theme=None
    )

# --- By category ------------------------------------------------------------
with right:
    st.subheader("By category")
    by_cat = monthly.groupby(
        ["category", "category_group"], as_index=False
    ).agg(spend=("spend", "sum"), txn_count=("txn_count", "sum"))
    by_cat["share"] = by_cat["spend"] / by_cat["spend"].sum()
    st.altair_chart(charts.category_bars(by_cat), width="stretch", theme=None)

with st.expander("Table view"):
    table = by_cat.sort_values("spend", ascending=False)
    table["per_month"] = table["spend"] / months
    st.dataframe(
        table[
            [
                "category",
                "category_group",
                "spend",
                "per_month",
                "share",
                "txn_count",
            ]
        ],
        hide_index=True,
        width="stretch",
        column_config={
            "category": "Category",
            "category_group": "Group",
            "spend": st.column_config.NumberColumn("Spend", format="dollar"),
            "per_month": st.column_config.NumberColumn(
                "Per month", format="dollar"
            ),
            "share": st.column_config.NumberColumn("Share", format="percent"),
            "txn_count": "Transactions",
        },
    )
