"""Bank and credit-card CSV export source (Chase, Amex).

Description: dlt source that reads the CSV exports downloaded from the
    Chase and American Express websites and loads one raw table per
    export layout: `chase_checking`, `chase_card`, and `amex`.
Usage: import `bank_csv_source` from a dlt pipeline; see
    ingest/pipelines/run_bank_csv.py.
Parameters: none at import time; the statements folder comes from the
    `FINANCE_STATEMENTS_ROOT` environment variable (see .env.example).
Returns: n/a (module defines a dlt source).

Notes
-----
Files live at `<statements_root>/<account_key>/*.csv`. The folder name
is the account key (matching transform/seeds/accounts.csv), and the
export layout is detected from the CSV header, not the folder name, so
a mis-filed file fails loudly rather than loading into the wrong table.

Each table's columns are declared up front and frozen with a dlt schema
contract. dlt's default is to evolve -- silently add a column when a
file has a new one -- but here a new column means the bank changed its
export format, and that should stop the load (and, via the refresh
runner, leave the live database untouched) until staging is updated.

Neither bank's export includes a stable transaction ID (Amex's
"Reference" only appears in the extended export), so each row is keyed
on a hash of (account, date, amount, description, occurrence_n).
`occurrence_n` numbers identical rows within one file, so two genuine
$5.00 coffees on the same day stay two rows, while the same
transaction appearing in two overlapping exports collapses to one on
merge.
"""

import csv
import hashlib
import os
import re
from collections import Counter
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator

import dlt

# Header columns that identify each export layout. A file matches a
# layout when its header contains every column listed.
LAYOUT_SIGNATURES = {
    "chase_checking": {"Details", "Posting Date", "Description", "Amount"},
    "chase_card": {"Transaction Date", "Post Date", "Description", "Amount"},
    # Amex's basic export is just these three; the extended export
    # ("include all additional transaction details") adds more.
    "amex": {"Date", "Description", "Amount"},
}

# Each layout's columns, snake_cased, exactly as the bank exports them.
# Declared up front (all text: typing is dbt staging's job) so every
# table exists with every column even before a file arrives -- e.g. the
# Amex extended-export columns before the first extended export.
LAYOUT_COLUMNS = {
    "chase_checking": (
        "details", "posting_date", "description", "amount", "type",
        "balance", "check_or_slip",
    ),
    "chase_card": (
        "transaction_date", "post_date", "description", "category", "type",
        "amount", "memo",
    ),
    # The basic export is date/description/amount; the extended export
    # ("include all additional transaction details") adds the rest.
    "amex": (
        "date", "description", "card_member", "account", "amount",
        "extended_details", "appears_on_your_statement_as", "address",
        "city_state", "zip_code", "country", "reference", "category",
    ),
}  # fmt: skip

# Columns this module adds to every row, on top of the bank's own.
METADATA_COLUMNS = {
    "txn_hash": {"data_type": "text", "nullable": False},
    "account_key": {"data_type": "text", "nullable": False},
    "occurrence_n": {"data_type": "bigint"},
    "source_file": {"data_type": "text"},
    "source_line": {"data_type": "bigint"},
    "extracted_at": {"data_type": "timestamp"},
}

# Per layout, the columns that make up the transaction-identity hash.
HASH_COLUMNS = {
    "chase_checking": ("posting_date", "description", "amount"),
    "chase_card": ("transaction_date", "description", "amount"),
    "amex": ("date", "description", "amount"),
}


def _snake_case(column: str) -> str:
    """Normalize a CSV header to a snake_case column name.

    Parameters
    ----------
    column : str
        Header as the bank wrote it, e.g. "Check or Slip #".

    Returns
    -------
    str
        e.g. "check_or_slip".
    """
    return re.sub(r"[^a-z0-9]+", "_", column.strip().lower()).strip("_")


def detect_layout(header: list[str]) -> str:
    """Identify which bank export layout a CSV header belongs to.

    Checked most-specific first, since every layout has "Description"
    and "Amount".

    Parameters
    ----------
    header : list of str
        The CSV's header row.

    Returns
    -------
    str
        One of the keys of `LAYOUT_SIGNATURES`.

    Raises
    ------
    ValueError
        If the header matches no known layout.
    """
    columns = {column.strip() for column in header}
    for layout, signature in LAYOUT_SIGNATURES.items():
        if signature <= columns:
            return layout
    raise ValueError(
        f"Unrecognized CSV header {header}; expected a Chase checking, "
        "Chase credit card, or Amex export."
    )


def _normalize_amount(raw: str) -> str:
    """Render an amount string canonically for hashing.

    Parameters
    ----------
    raw : str
        Amount as exported, e.g. "-12.5" or "1,204.00".

    Returns
    -------
    str
        Two-decimal string, e.g. "-12.50".
    """
    return str(Decimal(raw.replace(",", "").strip()).quantize(Decimal("0.01")))


def _txn_hash(account_key: str, identity: tuple[str, ...], n: int) -> str:
    """Build the stable transaction key.

    Parameters
    ----------
    account_key : str
        Folder name identifying the account.
    identity : tuple of str
        The layout's `HASH_COLUMNS` values for this row.
    n : int
        1-based occurrence of this identity within its file.

    Returns
    -------
    str
        Hex SHA-256 digest.
    """
    payload = "|".join((account_key, *identity, str(n)))
    return hashlib.sha256(payload.encode()).hexdigest()


def parse_statement(
    path: Path, account_key: str
) -> tuple[str, list[dict[str, Any]]]:
    """Parse one bank CSV export into raw transaction rows.

    Parameters
    ----------
    path : Path
        CSV file to read.
    account_key : str
        Account the file belongs to (its parent folder name).

    Returns
    -------
    tuple of (str, list of dict)
        The detected layout and its rows. Original columns are kept as
        strings, snake_cased; typing happens in dbt staging.
    """
    # utf-8-sig strips the BOM some exports start with.
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        layout = detect_layout(reader.fieldnames or [])
        extracted_at = datetime.now(timezone.utc).isoformat()
        seen: Counter[tuple[str, ...]] = Counter()
        rows = []
        for line_number, record in enumerate(reader, start=2):
            # Chase checking rows end with a trailing comma the header
            # lacks; DictReader files that extra field under None.
            record.pop(None, None)
            row = {
                _snake_case(key): (value.strip() if value else None)
                for key, value in record.items()
            }
            if not row.get("amount"):
                continue
            row["amount"] = _normalize_amount(row["amount"])
            identity = tuple(row[c] or "" for c in HASH_COLUMNS[layout])
            seen[identity] += 1
            row.update(
                txn_hash=_txn_hash(account_key, identity, seen[identity]),
                account_key=account_key,
                occurrence_n=seen[identity],
                # Relative to the statements root, never absolute: an
                # absolute path embeds the home directory (and so the OS
                # username) in every row and in anything exported.
                source_file=f"{account_key}/{path.name}",
                source_line=line_number,
                extracted_at=extracted_at,
            )
            rows.append(row)
    return layout, rows


def _statement_files(statements_root: str) -> Iterator[tuple[Path, str]]:
    """List every CSV under the statements root with its account key.

    Parameters
    ----------
    statements_root : str
        Folder containing one subfolder per account.

    Yields
    ------
    tuple of (Path, str)
        Each CSV path and its account key (parent folder name).
    """
    for path in sorted(Path(statements_root).glob("*/*.csv")):
        yield path, path.parent.name


@dlt.source(name="bank_csv")
def bank_csv_source(statements_root: str | None = None) -> Any:
    """dlt source with one resource (raw table) per export layout.

    Parameters
    ----------
    statements_root : str, optional
        Folder of per-account statement subfolders. Defaults to
        `FINANCE_STATEMENTS_ROOT`, else "data/statements".

    Returns
    -------
    list
        Resources `chase_checking`, `chase_card`, and `amex`.
    """
    root = statements_root or os.environ.get(
        "FINANCE_STATEMENTS_ROOT", "data/statements"
    )
    # Parse each file once, then hand each layout's rows to its resource.
    rows_by_layout: dict[str, list[dict[str, Any]]] = {
        layout: [] for layout in LAYOUT_COLUMNS
    }
    for path, account_key in _statement_files(root):
        layout, rows = parse_statement(path, account_key)
        rows_by_layout[layout].extend(rows)

    def make_resource(layout: str) -> Any:
        @dlt.resource(
            name=layout,
            write_disposition="merge",
            primary_key="txn_hash",
            columns={
                **{
                    column: {"data_type": "text", "nullable": True}
                    for column in LAYOUT_COLUMNS[layout]
                },
                **METADATA_COLUMNS,
            },
            schema_contract={"columns": "freeze"},
        )
        def resource() -> Iterator[Any]:
            # Create the table even when no file of this layout exists
            # yet, so dbt's source always resolves.
            yield dlt.mark.materialize_table_schema()
            yield from rows_by_layout[layout]

        return resource

    return [make_resource(layout) for layout in LAYOUT_COLUMNS]
