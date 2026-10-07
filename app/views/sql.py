"""SQL: read-only ad hoc queries against the warehouse.

Replaces reaching for `pixi run sql` / `pixi run ui` for quick looks.
Queries run on a read-only connection, so nothing here can change data.
"""

import duckdb
import streamlit as st

import data

st.title("SQL")

EXAMPLES = {
    "Biggest purchases this year": """SELECT txn_date, merchant_name, category, -amount AS spent
FROM main_marts.fct_transactions
WHERE amount < 0 AND NOT is_transfer
  AND txn_date >= date_trunc('year', current_date)
ORDER BY spent DESC
LIMIT 20""",
    "Spend by merchant": """SELECT merchant_name, category, count(*) AS txns,
       sum(spend_amount) AS spent
FROM main_marts.fct_transactions
WHERE is_spend
GROUP BY ALL
ORDER BY spent DESC""",
    "Month over month by category": """PIVOT (
    SELECT strftime(txn_month, '%Y-%m') AS month, category, spend
    FROM main_marts.mart_monthly_spend
)
ON month USING sum(spend)
GROUP BY category
ORDER BY category""",
    "Why was this categorized?": """SELECT raw_description, clean_description, matched_pattern,
       merchant_name, category
FROM main_marts.fct_transactions
WHERE raw_description ILIKE '%uber%'
LIMIT 50""",
}

pick = st.selectbox(
    "Start from an example", ["", *EXAMPLES], format_func=lambda k: k or "Blank"
)
sql = st.text_area(
    "Query",
    value=EXAMPLES.get(
        pick, "SELECT *\nFROM main_marts.fct_transactions\nLIMIT 100"
    ),
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
        SELECT table_schema AS schema, table_name AS name,
               lower(table_type) AS type
        FROM information_schema.tables
        WHERE table_schema IN ('main_marts', 'main_intermediate',
                               'main_staging', 'main_seeds', 'raw_bank')
          AND table_name NOT LIKE '\\_dlt%' ESCAPE '\\'
        ORDER BY schema = 'main_marts' DESC, schema, name
        """
    )
    st.dataframe(tables, hide_index=True, width="stretch")
    st.caption(
        "Start with **main_marts.fct_transactions**: one row per "
        "transaction, already cleaned and categorized."
    )
