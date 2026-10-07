# Using ownbooks with your own statements

## Setup

Requires [pixi](https://pixi.sh) (`brew install pixi`).

```bash
git clone https://github.com/jagriss/ownbooks.git && cd ownbooks
pixi install
pixi run install-hooks   # enable the data-leak guard (once per clone)
```

## Load your statements

1. **Export CSVs** from each account.
   - **Chase:** open the account → *Download account activity* → CSV.
     This works for checking and credit cards.
   - **Amex:** *Statements & Activity* → *Download* → CSV. Check
     *include all additional details* for the richer export.
2. **Name your accounts** in `transform/seeds/accounts.csv`, then drop
   each account's files in a folder of the same name:
   ```
   data/statements/chase_checking/Chase1234_Activity_20261007.CSV
   data/statements/chase_sapphire/Chase4321_Activity20261007.CSV
   data/statements/amex_gold/activity.csv
   ```
3. **Open the app** (`pixi run app`). New files show up in a banner at
   the top of every page. Click **Load**.
4. **Categorize.** Most transactions arrive already categorized from the
   bank's own labels. The Categorize page shows how much of your
   spending comes from your rules, from bank guesses, or neither, and
   lists every merchant without a rule, most money first:
   - **No category:** no rule and no bank label. Write a rule.
   - **Bank guesses:** the guess is prefilled. Save to confirm it, or
     pick another category.

   Each save rebuilds the warehouse. A dbt warning appears until less
   than 5% of spending is uncategorized. To change what a bank label
   maps to, edit `transform/seeds/bank_category_map.csv`.

Keep rules impersonal, since the seed CSVs are committed. Write
`ZELLE PAYMENT TO LANDLORD%`, not your landlord's name.

If you've been using dummy data, start fresh first:

```bash
rm data/statements/*/dummy_*.csv data/finance.duckdb
```

## Commands

| Command | Does |
|---|---|
| `pixi run app` | The app. Day to day, this is the only command you need. |
| `pixi run refresh` | Load new statements and rebuild from the command line. `--models` rebuilds without loading; `--rebuild` starts from an empty database and reloads every statement. |
| `pixi run sql` / `ui` | Read-only DuckDB shell or notebook UI. Neither blocks a refresh. |
| `pixi run demo` | Run the pipeline on test fixtures into `data/demo.duckdb` |
| `pixi run dummy-data` | Generate a year of synthetic statements |
| `pixi run test` | Unit tests for the CSV parser |
| `pixi run check-private` | Scan tracked files for financial data |
| `pixi run fmt` / `lint-sql` | Format Python and lint dbt SQL |

## Privacy notes

- The network is used at setup (`pixi install` downloads packages), and
  the optional DuckDB UI downloads its extension the first time it opens.
  Nothing leaves the device at runtime.
- The database isn't encrypted, so it's exactly as private as your
  laptop. Turn on FileVault (or your OS's disk encryption), and encrypt
  any backups that include `data/`.
