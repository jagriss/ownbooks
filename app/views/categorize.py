"""Categorize: turn uncategorized descriptions into merchant rules.

Pick a description, shape a rule (with a live preview of exactly which
transactions it will catch), save it to seeds/merchant_rules.csv, and
rebuild -- the loop that `pixi run todo` + hand-editing the CSV did.
All rules are also editable in bulk at the bottom.
"""

import pandas as pd
import streamlit as st

import data

st.title("Categorize")

uncat = data.query(
    """
    SELECT clean_description, txn_count, total_amount, last_seen,
           example_raw_description
    FROM main_marts.mart_uncategorized
    ORDER BY abs(total_amount) DESC
    """
)
cats = [c for c in data.categories() if c != "Uncategorized"]

total_spend = data.query(
    "SELECT sum(abs(spend_amount)) AS s FROM main_marts.fct_transactions"
).iloc[0]["s"]
uncat_spend = float(
    uncat.loc[uncat["total_amount"] < 0, "total_amount"].abs().sum()
)
pct = uncat_spend / float(total_spend or 1)
st.progress(
    min(1.0, 1 - pct),
    text=f"**{1 - pct:.0%}** of spend categorized · {len(uncat)} descriptions to go "
    f"({data.md(f'${uncat_spend:,.0f}')})",
)


# Seed files as they were before this run's edit, restored if the
# rebuild fails, so the CSVs never hold a rule the warehouse rejected.
_SEED_SNAPSHOT = {
    name: (data.SEEDS / f"{name}.csv").read_text()
    for name in ("merchant_rules", "categories")
}


def _restore_seeds() -> None:
    for name, text in _SEED_SNAPSHOT.items():
        (data.SEEDS / f"{name}.csv").write_text(text)


def _rebuild_and_rerun(message: str) -> None:
    data.refresh_with_status(
        ingest=False, success=message, on_failure=_restore_seeds
    )


# --- Pick a description -----------------------------------------------------
if uncat.empty:
    st.success("Everything is categorized.", icon=":material/task_alt:")
else:
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.subheader("Uncategorized")
        st.caption("Biggest money first. Select a row to write a rule for it.")
        picked = st.dataframe(
            uncat[
                ["clean_description", "txn_count", "total_amount", "last_seen"]
            ],
            hide_index=True,
            width="stretch",
            height=460,
            on_select="rerun",
            selection_mode="single-row",
            key="uncat_table",
            column_config={
                "clean_description": "Description",
                "txn_count": st.column_config.NumberColumn(
                    "Txns", width="small"
                ),
                "total_amount": st.column_config.NumberColumn(
                    "Total", format="dollar"
                ),
                "last_seen": st.column_config.DateColumn(
                    "Last seen", format="MMM D"
                ),
            },
        )
        rows = picked.selection.rows
        selected = uncat.iloc[rows[0] if rows else 0]

    # --- Shape the rule -------------------------------------------------------
    with right:
        desc = selected["clean_description"]
        st.subheader("New rule")
        st.caption(f"Bank shows it as `{selected['example_raw_description']}`")
        k = f"rule::{desc}"  # per-description widget state
        pattern = st.text_input(
            "Pattern",
            value=f"{desc}%",
            key=f"{k}::pattern",
            help="Matched case-insensitively against the cleaned description. "
            "% matches anything: `COSTCO%` catches every Costco store.",
        )
        c1, c2 = st.columns([3, 2])
        merchant = c1.text_input(
            "Merchant name", value=desc.title(), key=f"{k}::merchant"
        )
        category = c2.selectbox(
            "Category",
            [*cats, "＋ New category…"],
            index=None,
            placeholder="Choose…",
            key=f"{k}::category",
        )
        new_cat = None
        if category == "＋ New category…":
            n1, n2, n3 = st.columns([2, 2, 1], vertical_alignment="bottom")
            name = n1.text_input("Category name", key=f"{k}::newcat")
            groups = sorted(
                data.read_seed("categories")["category_group"].unique()
            )
            group = n2.selectbox(
                "Group",
                groups,
                index=None,
                placeholder="Choose or type new…",
                key=f"{k}::newgroup",
                accept_new_options=True,
            )
            essential = n3.checkbox("Essential", key=f"{k}::essential")
            new_cat = {
                "category": name.strip(),
                "category_group": group,
                "is_essential": str(essential).lower(),
                "is_spend": "true",
            }
            category = name.strip() or None
            if category and not group:
                category = None  # incomplete until a group is chosen
        with st.expander("Advanced"):
            priority = st.number_input(
                "Priority",
                1,
                99,
                10,
                key=f"{k}::priority",
                help="Lower wins when several rules match. Use < 10 for a specific "
                "rule that must beat a general one (UBER%EATS% at 5 beats UBER% at 10).",
            )

        # Live preview of what the pattern catches.
        matches = (
            data.query(
                """
            SELECT txn_date, clean_description, category, amount
            FROM main_marts.fct_transactions
            WHERE clean_description ILIKE ?
            ORDER BY txn_date DESC
            """,
                (pattern,),
            )
            if pattern.strip()
            else pd.DataFrame()
        )
        recat = (
            matches[matches["category"] != "Uncategorized"]
            if not matches.empty
            else matches
        )
        if matches.empty:
            st.warning(
                "This pattern matches no transactions.",
                icon=":material/search_off:",
            )
        else:
            others = matches["clean_description"].nunique() - 1
            st.markdown(
                f"Matches **{len(matches)} transactions** "
                f"({data.md(f'${matches['amount'].abs().sum():,.2f}')})"
                + (
                    f" across **{others + 1} descriptions**"
                    if others > 0
                    else ""
                )
            )
            if not recat.empty:
                st.caption(
                    f"{len(recat)} of them already have a category "
                    f"({data.md(', '.join(sorted(recat['category'].unique())))}); they only "
                    "change if this rule's priority beats their current rule."
                )
            st.dataframe(
                matches.head(50),
                hide_index=True,
                width="stretch",
                height=180,
                column_config={
                    "txn_date": st.column_config.DateColumn(
                        "Date", format="MMM D, YYYY"
                    ),
                    "clean_description": "Description",
                    "category": "Current",
                    "amount": st.column_config.NumberColumn(
                        "Amount", format="dollar"
                    ),
                },
            )

        rules = data.read_seed("merchant_rules")
        problems = []
        if not pattern.strip():
            problems.append("Enter a pattern.")
        elif pattern.strip().upper() in rules["pattern"].str.upper().tolist():
            problems.append(
                "A rule with this pattern already exists; edit it below."
            )
        if not merchant.strip():
            problems.append("Enter a merchant name.")
        if not category:
            problems.append("Choose a category.")
        elif new_cat and category in data.categories():
            problems.append(
                f"Category {category!r} already exists; pick it from the list."
            )

        if st.button(
            "Save rule & rebuild",
            type="primary",
            icon=":material/save:",
            disabled=bool(problems),
            help=" ".join(problems) or None,
            width="stretch",
        ):
            if new_cat:
                cat_df = pd.concat(
                    [data.read_seed("categories"), pd.DataFrame([new_cat])]
                )
                data.write_seed("categories", cat_df, data.CATEGORY_COLUMNS)
            new_rule = {
                "pattern": pattern.strip(),
                "merchant_name": merchant.strip(),
                "category": category,
                "priority": str(priority),
            }
            data.write_seed(
                "merchant_rules",
                pd.concat([rules, pd.DataFrame([new_rule])]),
                data.RULE_COLUMNS,
            )
            _rebuild_and_rerun(
                f"Saved {data.md(pattern.strip())} → {data.md(category)}"
            )
        elif problems and category:
            st.caption(" ".join(problems))

# --- All rules ----------------------------------------------------------------
st.divider()
st.subheader("All rules")
st.caption(
    "Edit cells, add rows at the bottom, or select rows and press Delete. "
    "Changes apply when you save."
)
rules = data.read_seed("merchant_rules")
rules["priority"] = pd.to_numeric(rules["priority"])
edited = st.data_editor(
    rules,
    num_rows="dynamic",
    hide_index=True,
    width="stretch",
    key="rules_editor",
    column_config={
        "pattern": st.column_config.TextColumn("Pattern", required=True),
        "merchant_name": st.column_config.TextColumn("Merchant", required=True),
        "category": st.column_config.SelectboxColumn(
            "Category", options=data.categories(), required=True
        ),
        "priority": st.column_config.NumberColumn(
            "Priority",
            min_value=1,
            max_value=99,
            step=1,
            default=10,
            required=True,
        ),
    },
)
changed = not edited.reset_index(drop=True).equals(rules.reset_index(drop=True))
if st.button(
    "Save rules & rebuild", icon=":material/save:", disabled=not changed
):
    clean = edited.dropna(subset=["pattern", "merchant_name", "category"])
    clean = clean[clean["pattern"].str.strip() != ""]
    dupes = clean["pattern"].str.upper().duplicated()
    if dupes.any():
        st.error(
            f"Duplicate patterns: {data.md(', '.join(clean.loc[dupes, 'pattern']))}"
        )
    else:
        clean = clean.assign(priority=clean["priority"].fillna(10).astype(int))
        data.write_seed("merchant_rules", clean, data.RULE_COLUMNS)
        _rebuild_and_rerun(f"Saved {len(clean)} rules")
