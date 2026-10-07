# ownbooks

**Personal finance that never leaves your laptop.**

ownbooks turns the CSV exports from my Chase and Amex accounts into
clean, categorized, deduplicated transactions, then shows them in a
small app where I can explore spending, catch subscriptions, and teach
it new categories with a click. It's a full data stack (ingestion,
warehouse, transformation, tests, and an app) that runs entirely on my
own machine.

![Overview page](docs/images/overview.png)

<sub>Screenshots show sample data, not real transactions.</sub>

## How it's built

- Bank exports load through a dlt pipeline that recognizes each format
  from its header, never duplicates a transaction, and stops if a bank
  changes its export format.
- A layered dbt project turns them into tested tables: 55 data tests,
  every model documented, and one SQL style enforced by a linter.
- Every rebuild runs on a copy of the database and is swapped in only if
  all tests pass, so a bad build never reaches the app.
- Nothing leaves the laptop at runtime, which I checked with a logging
  proxy, and a pre-commit hook keeps financial data out of git.
- The app writes back to the pipeline: categorizing a merchant edits a
  dbt seed and rebuilds the warehouse.

## Why I built it

Budgeting apps want your bank credentials and categorize transactions
however they like. I wanted the opposite: my data, on my device, under
my control. Every category comes from a rule in a CSV file or, until I
write one, from the bank's own label, and each transaction records
which, so I can always see why it landed where it did.

## What it does

| | |
|---|---|
| **Loads Chase and Amex exports** | Detects each export format from its header. Re-downloading overlapping date ranges never creates duplicates. |
| **Cleans and categorizes** | Strips the noise from bank descriptions (`SQ *BLUE BOTTLE COFFEE` → `BLUE BOTTLE COFFEE`, `WHOLEFDS MKT 10234` → `WHOLEFDS MKT`), then applies prioritized merchant rules, falling back to the bank's own category. |
| **Understands money flows** | Normalizes every bank to one sign convention and pairs card payments with the checking withdrawals that paid them, so paying a card isn't counted as spending twice. |
| **Finds subscriptions** | Flags charges that recur monthly for a near-constant amount, with what's due next week and what looks cancelled. |
| **Categorizes interactively** | Pick a merchant, preview exactly which transactions a rule would catch, save, and the warehouse rebuilds. Bank guesses come prefilled. |

<table>
<tr>
<td><img src="docs/images/categorize.png" alt="Categorize page"></td>
<td><img src="docs/images/subscriptions.png" alt="Subscriptions page"></td>
</tr>
<tr>
<td align="center"><sub>Categorize: confirm a bank guess or write a rule, with a live preview</sub></td>
<td align="center"><sub>Subscriptions: recurring charges and renewals</sub></td>
</tr>
</table>

## Architecture

```
 data/statements/<account>/*.csv          Chase checking · Chase card · Amex
            │
            │  dlt  ─ detect layout from header, hash each row, merge on key
            ▼
 raw_bank.chase_checking · chase_card · amex    one table per bank, columns frozen
            │
            │  dbt staging       ─ type columns, one sign convention per bank
            │  dbt intermediate  ─ union → clean descriptions → apply rules
            │                      → pair transfers between my accounts
            │      ▲
            │      └── seeds: merchant_rules · bank_category_map · categories · accounts
            ▼                                       ▲
 marts: fct_transactions · dim_merchants           │ the app writes rules here
        mart_monthly_spend · mart_subscriptions     │
        mart_uncategorized                          │
            │                                       │
            ▼                                       │
 Streamlit app  ────────────────────────────────────┘
```

| Tool | Role | Why this one |
|---|---|---|
| [**pixi**](https://pixi.sh) | Environments and tasks | One lockfile pins Python, DuckDB, dbt, and Streamlit together, and it doubles as the task runner. |
| [**dlt**](https://dlthub.com) | Ingestion | Typed, idempotent `merge` loads with schema contracts, from plain Python generators. |
| [**DuckDB**](https://duckdb.org) | Warehouse | An analytical database in a single file: no server, fast, easy to back up. |
| [**dbt**](https://www.getdbt.com) (Fusion engine) | Transformation and tests | Every table is a tested SQL `SELECT`; rules and categories live as seeds. |
| [**Streamlit**](https://streamlit.io) + Altair | App | A Python-only UI that can also write back to the pipeline. |

## Engineering decisions

### 1. One raw table per bank, with a frozen schema

dlt loads each export format into its own table, with every original
column kept as text; dbt staging handles typing, one model per table.

- **A table per source, not one wide table.** My first version put
  every bank into a single table, so columns like `type` and `category`
  meant different things depending on the row.
- **Tables exist before the data does.** `dlt.mark.materialize_table_schema()`
  creates each table even with no statements from that bank yet, so
  dbt's sources always resolve.
- **Columns are frozen with a dlt schema contract.** dlt's default is to
  add new columns silently. Here a new column means the bank changed its
  export format, so the load fails with an error naming the bank and the
  column. Tested by adding a fake `Rewards Points` column to a Chase
  export.

### 2. A synthetic transaction key

Neither bank exports a stable transaction ID, so each row is keyed on a
hash of `(account, date, amount, description, occurrence_n)`, where
`occurrence_n` numbers identical rows within one file. Two genuine
$6.50 coffees on the same day stay two rows, while the same coffee in
two overlapping exports collapses to one.

### 3. One sign convention, enforced by a test

Chase signs amounts from the account holder's side; Amex signs them from
its own, with purchases positive. Staging flips Amex so that everywhere
downstream **negative means money out**, and a data test fails the build
if a bank's sign is ever backwards.

### 4. Rules in a CSV, with the bank's label as fallback

Categories come from `merchant_rules.csv` (an `ILIKE` pattern, merchant
name, category, and priority) matched against a cleaned description.
It's deterministic, diffable in git, and explainable: every transaction
records the pattern that matched it.

For the long tail, any transaction without a rule takes the bank's own
category, mapped onto mine through `bank_category_map.csv`. On a year of
synthetic data this cut uncategorized spend from about 43% to 3% without
writing a rule. I considered machine learning here: with one person's
data, a model mostly re-learns what the rules and bank labels already
know, and gives up determinism.

### 5. Transfers are paired, not just labeled

A card payment appears twice: leaving checking and arriving on the card.
`int_transactions__transfers` pairs the two sides by opposite amount,
different account, and a 5-day window, so neither side counts as spend.
A test warns when one side has no match.

### 6. Subscription detection is strict on purpose

A subscription is a merchant charging 3+ times, *every* gap 25–35 days,
with amounts varying less than 5%. A looser first version (average gaps,
10% tolerance) flagged Whole Foods and Shell.

### 7. Build on a copy, swap in atomically

DuckDB allows one writer, and a writer can't open a file another process
has open, so building in place let the app or a SQL shell block a
refresh. Every refresh instead copies the database, runs dlt and
`dbt build` against the copy, and `os.replace()`s it over the live file
only if every test passes. Readers see the old database or the new one,
never a half-built one, and a failed build changes nothing. If a rule
saved in the app breaks the build, it's removed from the CSV again.

*The gotcha:* DuckDB names the catalog after the file stem, and dbt
writes that name into every view, so the copy must keep the same
filename (in a different folder) or the views break after the swap.

### 8. Privacy in layers

- **Off the network.** dlt and dbt send usage telemetry by default, and
  dbt Fusion checks for updates on every run. All three are disabled in
  project config, the environment, and the refresh runner. Verified with
  a proxy that logs and drops connections: 8 outbound calls per refresh
  before, zero after, across the pipeline, app server, and browser.
- **Out of git.** `.gitignore` covers `data/` and every statement or
  warehouse format in any letter case (Chase exports `.CSV`, which a
  Linux clone would otherwise miss). A pre-commit hook also catches
  `git add -f`, oversized fixtures, Luhn-valid card numbers, and email
  addresses.
- **Off the LAN.** The app binds to `localhost` only.

The database isn't encrypted; it's exactly as private as the laptop's
disk encryption.

### 9. One SQL style, enforced by the linter

Every model has the same shape: leading commas, explicit column lists
in every CTE, and a `final` CTE with no logic. Each model has a YML
beside it describing every column and testing its key, and the only
Jinja is `{{ ref() }}` and `{{ source() }}`, so the SQL you read is the
SQL that runs. `.sqlfluff` enforces the style.

```sql
WITH charges AS (
    SELECT
        merchant_name
        ,category
        ,-amount AS charge_amount
    FROM {{ ref('fct_transactions') }}
    WHERE is_spend AND amount < 0
)

,final AS (
    SELECT
        merchant_name
        ,category
        ,charge_amount
    FROM charges
)

SELECT
*
FROM final
```

### 10. Charts: one hue and emphasis, not a rainbow

The charts use one accent color plus gray. To compare a category with
the total, you highlight it, and it turns blue over gray bars, instead
of a 12-color stacked bar.

## Testing

- **Unit tests** cover the parser against synthetic fixtures: format
  detection, Chase's trailing commas, BOM handling, same-day duplicates,
  overlapping exports hashing identically, and every parsed column being
  declared for its frozen table.
- **dbt** runs 55 data tests on every rebuild, and a failure blocks the
  swap:

| Test | Catches |
|---|---|
| `unique` / `not_null` on every model's key | a deduplication regression or a broken grain |
| `relationships` on `account_key` and `category` | a statements folder or rule with no matching seed row |
| `accepted_values` on `category_source` | a category from anything other than `rule`, `bank`, or `none` |
| `assert_card_payments_are_inflows` | a bank's sign convention flipped |
| `assert_transfers_are_matched` (warn) | a payment whose other side isn't exported yet |
| `assert_uncategorized_spend_under_5pct` (warn) | rules left to write |

- **A synthetic data generator** produces a year of realistic Chase and
  Amex exports (overlapping files, refunds, duplicates, card payments)
  for end-to-end runs without real data.

## Run it

Requires [pixi](https://pixi.sh). This runs the full stack on synthetic
data:

```bash
git clone https://github.com/jagriss/ownbooks.git && cd ownbooks
pixi install
pixi run dummy-data   # a year of synthetic Chase + Amex exports
pixi run app          # http://localhost:8501, then click "Load"
```

To use it with real statements, see [docs/USAGE.md](docs/USAGE.md).

## What I'd build next

- More banks: each one is a header signature and column list, a source
  entry, and one staging model.
- Rule suggestions from a small local model, for merchants the bank
  doesn't label.
- Monthly budgets per category group, with pace-to-date on the Overview.
