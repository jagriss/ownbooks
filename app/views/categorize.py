"""Categorize: turn descriptions without a rule into merchant rules.

Pick a description, shape a rule (with a live preview of exactly which
transactions it will catch), save it to seeds/merchant_rules.csv, and
rebuild. Descriptions the bank-category fallback already guessed are
listed too, with the guess pre-filled, so confirming one is one click.
All rules are also editable in bulk at the bottom.
"""

import pandas as pd
import streamlit as st

import data

st.title("Categorize")

todo = data.query(
    f"""
    SELECT
    clean_description
    ,bank_guess
    ,txn_count
    ,total_amount
    ,last_seen
    ,example_raw_description
    FROM {data.CATALOG}.main_marts.mart_uncategorized
    ORDER BY bank_guess IS NOT NULL, abs(total_amount) DESC
    """
)
cats = [c for c in data.categories() if c != "Uncategorized"]

# Coverage by where each transaction's category came from.
by_source = data.query(
    f"""
    SELECT
    category_source
    ,sum(abs(spend_amount)) AS spend
    FROM {data.CATALOG}.main_marts.fct_transactions
    WHERE is_spend
    GROUP BY category_source
    """
).set_index("category_source")["spend"]
total = float(by_source.sum() or 1)
share = {
    src: float(by_source.get(src, 0)) / total
    for src in ("rule", "bank", "none")
}
st.progress(
    min(1.0, share["rule"] + share["bank"]),
    text=f"**{share['rule'] + share['bank']:.0%}** of spend categorized: "
    f"{share['rule']:.0%} by your rules, {share['bank']:.0%} by bank guess · "
    f"{share['none']:.0%} uncategorized",
)

view = st.segmented_control(
    "Show",
    ["No category", "Bank guesses", "All"],
    default="No category" if todo["bank_guess"].isna().any() else "All",
    label_visibility="collapsed",
)
uncat = (
    {
        "No category": todo[todo["bank_guess"].isna()],
        "Bank guesses": todo[todo["bank_guess"].notna()],
    }
    .get(view, todo)
    .reset_index(drop=True)
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
if todo.empty:
    st.success("Every description has a rule.", icon=":material/task_alt:")
elif uncat.empty:
    st.success(f"Nothing in “{view}”.", icon=":material/task_alt:")
else:
    left, right = st.columns([1, 1], gap="large")
    with left:
        st.subheader("Needs a rule")
        st.caption("Biggest money first. Select a row to write a rule for it.")
        picked = st.dataframe(
            uncat[
                [
                    "clean_description",
                    "bank_guess",
                    "txn_count",
                    "total_amount",
                    "last_seen",
                ]
            ],
            hide_index=True,
            width="stretch",
            height=460,
            on_select="rerun",
            selection_mode="single-row",
            key="uncat_table",
            column_config={
                "clean_description": "Description",
                "bank_guess": st.column_config.TextColumn(
                    "Bank guess",
                    help="Category from the bank's own label, used until "
                    "a rule covers this description",
                ),
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
        guess = (
            selected["bank_guess"] if pd.notna(selected["bank_guess"]) else None
        )
        st.subheader("New rule")
        st.caption(f"Bank shows it as `{selected['example_raw_description']}`")
        if guess:
            st.caption(
                f"Currently **{data.md(guess)}**, from the bank's category. "
                "Save to confirm it, or pick another."
            )
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
            index=cats.index(guess) if guess in cats else None,
            placeholder="Choose…",
            key=f"{k}::category",
        )
        new_cat = None
        if category == "＋ New category…":
            n1, n2, n3 = st.columns([2, 2, 1], vertical_alignment="bottom")
            name = n1.text_input("Category name", key=f"{k}::newcat")
            # "Uncategorized" is a status, not a group to file things under.
            groups = sorted(
                g
                for g in data.read_seed("categories")["category_group"].unique()
                if g != "Uncategorized"
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
                f"""
                SELECT
                txn_date
                ,clean_description
                ,category
                ,category_source
                ,amount
                FROM {data.CATALOG}.main_marts.fct_transactions
                WHERE clean_description ILIKE ?
                ORDER BY txn_date DESC
                """,
                (pattern,),
            )
            if pattern.strip()
            else pd.DataFrame()
        )
        # Rule-categorized matches only change if this rule outranks
        # theirs; bank guesses are always replaced by any rule.
        ruled = (
            matches[matches["category_source"] == "rule"]
            if not matches.empty
            else matches
        )
        guessed = (
            matches[matches["category_source"] == "bank"]
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
            if not guessed.empty:
                st.caption(
                    f"{len(guessed)} currently use the bank's guess; this "
                    "rule replaces it."
                )
            if not ruled.empty:
                st.caption(
                    f"{len(ruled)} already match another rule "
                    f"({data.md(', '.join(sorted(ruled['category'].unique())))}); "
                    "they only change if this rule's priority beats it."
                )
            st.dataframe(
                matches.drop(columns="category_source").head(50),
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
