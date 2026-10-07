"""SQL: read-only ad hoc queries against the warehouse.

Queries run on a read-only connection, so nothing here can change data.
"""

import duckdb
import streamlit as st

import data

st.title("SQL")

FCT = f"{data.CATALOG}.main_marts.fct_transactions"
MONTHLY = f"{data.CATALOG}.main_marts.mart_monthly_spend"

EXAMPLES = {
    "Biggest purchases this year": f"""SELECT
txn_date
,merchant_name
,category
,-amount AS spent
FROM {FCT}
WHERE amount < 0 AND NOT is_transfer
    AND txn_date >= date_trunc('year', current_date)
ORDER BY spent DESC
LIMIT 20""",
    "Spend by merchant": f"""SELECT
merchant_name
,category
,count(*) AS txns
,sum(spend_amount) AS spent
FROM {FCT}
WHERE is_spend
GROUP BY ALL
ORDER BY spent DESC""",
    "Month over month by category": f"""WITH monthly AS (
    SELECT
        strftime(txn_month, '%Y-%m') AS month
        ,category
        ,spend
    FROM {MONTHLY}
)

PIVOT monthly
ON month USING sum(spend)
GROUP BY category
ORDER BY category""",
    "Why was this categorized?": f"""SELECT
raw_description
,clean_description
,matched_pattern
,merchant_name
,category
,category_source
FROM {FCT}
WHERE raw_description ILIKE '%uber%'
LIMIT 50""",
}

pick = st.selectbox(
    "Start from an example", ["", *EXAMPLES], format_func=lambda k: k or "Blank"
)
sql = st.text_area(
    "Query",
    value=EXAMPLES.get(pick, f"SELECT\n*\nFROM {FCT}\nLIMIT 100"),
    height=200,
    key=f"sql::{pick}",
    label_visibility="collapsed",
)
run = st.button("Run", type="primary", icon=":material/play_arrow:")

if run or st.session_state.get("sql_last") == sql:
    st.session_state["sql_last"] = sql
    try:
        result = data.query(sql)
    except duckdb.Error as error:
        st.error(str(error).split("\n")[0], icon=":material/error:")
    else:
        st.caption(f"{len(result):,} rows")
        st.dataframe(result, hide_index=True, width="stretch", height=480)
        st.download_button(
            "Download CSV", result.to_csv(index=False), file_name="query.csv",
            mime="text/csv", icon=":material/download:",
        )  # fmt: skip

with st.expander("Tables"):
    tables = data.query(
        """
        SELECT
        table_catalog || '.' || table_schema AS schema
        ,table_name AS name
        ,lower(table_type) AS type
        FROM system.information_schema.tables
        WHERE table_catalog = ?
            AND table_schema IN (
                'main_marts', 'main_intermediate', 'main_staging',
                'main_seeds', 'raw_bank'
            )
            AND table_name NOT LIKE '\\_dlt%' ESCAPE '\\'
        ORDER BY table_schema = 'main_marts' DESC, table_schema, table_name
        """,
        (data.DB_PATH.stem,),
    )
    st.dataframe(tables, hide_index=True, width="stretch")
    st.caption(
        f"Start with **{data.md(FCT)}**: one row per "
        "transaction, already cleaned and categorized."
    )
