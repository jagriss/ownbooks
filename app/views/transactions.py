"""Transactions: searchable, filterable explorer over fct_transactions."""

import streamlit as st

import data

start, end = st.session_state["period"]
st.title("Transactions")

txns = data.query(
    f"""
    SELECT
    txn_date
    ,merchant_name
    ,category
    ,category_source
    ,category_group
    ,amount
    ,account_name
    ,is_transfer
    ,raw_description
    ,clean_description
    ,matched_pattern
    FROM {data.CATALOG}.main_marts.fct_transactions
    WHERE txn_date BETWEEN ? AND ?
    ORDER BY txn_date DESC, txn_id
    """,
    (start, end),
)

f1, f2, f3, f4 = st.columns([3, 2, 2, 1], vertical_alignment="bottom")
search = f1.text_input(
    "Search",
    placeholder="Merchant or description",
    label_visibility="collapsed",
)
accounts = f2.multiselect(
    "Accounts",
    sorted(txns["account_name"].dropna().unique()),
    placeholder="All accounts",
    label_visibility="collapsed",
)
cats = f3.multiselect(
    "Categories",
    sorted(txns["category"].unique()),
    placeholder="All categories",
    label_visibility="collapsed",
)
show_transfers = f4.toggle(
    "Transfers", value=False, help="Card payments between your own accounts"
)

view = txns
if search:
    needle = search.lower()
    view = view[
        view["merchant_name"].str.lower().str.contains(needle, regex=False)
        | view["raw_description"].str.lower().str.contains(needle, regex=False)
    ]
if accounts:
    view = view[view["account_name"].isin(accounts)]
if cats:
    view = view[view["category"].isin(cats)]
if not show_transfers:
    view = view[~view["is_transfer"]]

out = -view.loc[view["amount"] < 0, "amount"].sum()
inflow = view.loc[view["amount"] > 0, "amount"].sum()
m1, m2, m3 = st.columns(3, border=True)
m1.metric("Transactions", f"{len(view):,}")
m2.metric("Money out", f"${out:,.2f}")
m3.metric("Money in", f"${inflow:,.2f}")

st.dataframe(
    view.drop(columns=["is_transfer", "clean_description"]),
    hide_index=True,
    width="stretch",
    height=560,
    column_config={
        "txn_date": st.column_config.DateColumn("Date", format="MMM D, YYYY"),
        "merchant_name": "Merchant",
        "category": "Category",
        "category_group": "Group",
        "amount": st.column_config.NumberColumn(
            "Amount", format="dollar", help="Negative = money out"
        ),
        "account_name": "Account",
        "raw_description": st.column_config.TextColumn(
            "Bank description", width="large"
        ),
        "category_source": st.column_config.TextColumn(
            "Source",
            help="rule = your merchant rule · bank = the bank's own "
            "category (seeds/bank_category_map.csv) · none = uncategorized",
        ),
        "matched_pattern": st.column_config.TextColumn(
            "Rule", help="The merchant_rules pattern that categorized it"
        ),
    },
)
st.download_button(
    "Download CSV",
    view.to_csv(index=False),
    file_name="transactions.csv",
    mime="text/csv",
    icon=":material/download:",
)
