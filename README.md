# finance-categorizer

Turns Chase and Amex CSV exports into categorized, deduplicated
transactions with monthly spend and subscription detection, all in a
local DuckDB file.

```
data/statements/<account_key>/*.csv
        │  dlt (ingest/sources/bank_csv.py): detect layout from header,
        │  hash each row, merge on txn_hash
        ▼
raw_bank.transactions            one table, all banks, all text
        │  dbt staging: type columns, normalize sign (negative = money out)
        ▼
int_transactions__unioned → __cleaned → __categorized → __transfers
        │                        ▲
        │        seeds/merchant_rules.csv, categories.csv, accounts.csv
        ▼
main_marts.fct_transactions, mart_monthly_spend, mart_subscriptions,
dim_merchants, mart_uncategorized (your to-do list)
```

## Quick start

```bash
pixi install
pixi run demo    # full run on synthetic fixtures into data/demo.duckdb
pixi run test    # parser unit tests
```

## Using it with your real exports

1. **Export CSVs.**
   - Chase: open the account, choose **Download account activity**, then **CSV**. This works for both checking and cards.
   - Amex: go to **Statements & Activity**, then **Download**, then **CSV**. Check *include all additional details* if you want the Reference and Category columns.
2. **Name your accounts.** Edit `transform/seeds/accounts.csv`. Each `account_key` must match a folder name:
   ```
   data/statements/chase_checking/Chase1234_Activity_20261007.csv
   data/statements/chase_sapphire/Chase4321_Activity20261007.csv
   data/statements/amex_gold/activity.csv
   ```
   The layout is detected from each file's header, so folder names are
   yours to choose. A folder without a matching `accounts.csv` row fails
   the `relationships` test.
3. **Run the pipeline.**
   ```bash
   pixi run elt
   ```
   Ingesting is idempotent. Leave old files in place, and overlapping
   date ranges are deduplicated.
4. **Categorize.**
   ```bash
   pixi run todo
   ```
   For each description it lists, add a row to
   `transform/seeds/merchant_rules.csv`, then run `pixi run dbt-build`
   and repeat. The `assert_uncategorized_spend_under_5pct` test warns
   until you are mostly done.

## Rules

`merchant_rules.csv` patterns are `ILIKE` patterns (`%` = anything) matched
against `clean_description`. That is the bank's description uppercased,
with POS prefixes (`SQ *`, `TST*`), ACH IDs, and store numbers stripped:
`SQ *BLUE BOTTLE COFFEE` becomes `BLUE BOTTLE COFFEE`, and
`WHOLEFDS MKT 10234` becomes `WHOLEFDS MKT`. The lowest `priority` wins,
so give specific rules (`UBER%EATS%`, 5) a lower number than general ones
(`UBER%`, 10).

Transfers between your own accounts, such as card payments, get the
`Transfer` category. `int_transactions__transfers` then pairs the two
sides (opposite amounts, different accounts, within 5 days), so neither
side counts as spend.

## Tests worth knowing

| test | catches |
|---|---|
| `relationships` on `account_key` | a statements folder with no `accounts.csv` row |
| `relationships` on `category` | a rule using a category missing from `categories.csv` |
| `assert_card_payments_are_inflows` | a sign convention flipped the wrong way for a bank |
| `assert_transfers_are_matched` (warn) | a payment whose other side hasn't been exported |
| `assert_uncategorized_spend_under_5pct` (warn) | rules left to write |

## Privacy

- **Statements and the database can't be committed.** There are two layers:
  1. `.gitignore` ignores all of `data/` and every statement or warehouse
     format (`.csv`, `.pdf`, `.ofx`, `.qfx`, `.xlsx`, `.duckdb`, ...)
     anywhere in the repo, in any letter case. The only exceptions are
     `transform/seeds/*.csv` and the synthetic fixtures.
  2. A pre-commit hook (`scripts/check_private_data.py`) also catches
     `git add -f`. It blocks anything under `data/`, those formats, CSVs
     outside the two allowed folders, fixture CSVs over 8 KB, and any file
     containing a card-number-like value or a real email address. **Turn it
     on once per clone:**
     ```bash
     pixi run install-hooks
     ```
     `pixi run check-private` scans every tracked file. `git commit
     --no-verify` skips the hook, so don't use it in this repo.
- **Seeds are committed, so keep them impersonal.** Merchant rules for
  person-to-person payments (Zelle, Venmo) shouldn't include real names.
  Write `ZELLE PAYMENT TO LANDLORD%`, not the landlord's name.
- **No personal identifiers in code.** Authorship lives in git history,
  not in file headers or `pixi.toml`. Stored paths (`source_file`) are
  relative to the statements folder, so the database doesn't contain
  your home directory.
- **Commit identity.** Before pushing to a public remote, set this repo's
  commit email to your GitHub no-reply address (GitHub → Settings →
  Emails → "Keep my email addresses private"):
  ```bash
  git config user.email "<id>+<username>@users.noreply.github.com"
  ```
- **Fixtures and dummy data are synthetic.** Account suffixes like `1234`
  and `-41007` are made up; keep it that way if you add fixtures.
