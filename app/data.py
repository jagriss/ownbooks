"""Data access and pipeline actions for the Streamlit app.

Description: Read-only DuckDB queries (cached until the warehouse file
    is replaced), seed CSV read/write, new-statement detection, and the
    refresh action. The app never writes to the warehouse: refreshes
    build a copy and swap it in (ingest/refresh.py), so the app's
    short read-only connections never conflict with them.
Usage: imported by app/app.py and app/views/*.py.
"""

import csv
import os
import re
import sys
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # so the app can import the ingest package
from ingest.refresh import RefreshResult, refresh  # noqa: E402

DB_PATH = Path(
    os.environ.get("FINANCE_DUCKDB_PATH", ROOT / "data" / "finance.duckdb")
)
STATEMENTS = Path(
    os.environ.get("FINANCE_STATEMENTS_ROOT", ROOT / "data" / "statements")
)
SEEDS = ROOT / "transform" / "seeds"
RULE_COLUMNS = ["pattern", "merchant_name", "category", "priority"]
CATEGORY_COLUMNS = ["category", "category_group", "is_essential", "is_spend"]


def db_exists() -> bool:
    return DB_PATH.exists()


def _db_version() -> tuple[int, int]:
    """Changes whenever a refresh swaps in a new file; busts the cache."""
    if not DB_PATH.exists():
        return (0, 0)
    stat = DB_PATH.stat()
    return (stat.st_ino, stat.st_mtime_ns)


@st.cache_data(show_spinner=False)
def _cached_query(sql: str, params: tuple, _version: tuple) -> pd.DataFrame:
    with duckdb.connect(str(DB_PATH), read_only=True) as con:
        return con.execute(sql, list(params)).df()


def query(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a read-only query; cached until the database file changes."""
    return _cached_query(sql, params, _db_version())


def md(text: object) -> str:
    """Escape text for st.markdown-family calls. Without this, two "$"
    in one string render as LaTeX, and "*" in merchant names like
    "OPENAI *CHATGPT" toggles italics."""
    return re.sub(r"([\\`*_{}\[\]<>()#+\-.!|$~])", r"\\\1", str(text))


# --- seeds ---------------------------------------------------------------


def read_seed(name: str) -> pd.DataFrame:
    return pd.read_csv(SEEDS / f"{name}.csv", dtype=str, keep_default_na=False)


def write_seed(name: str, df: pd.DataFrame, columns: list[str]) -> None:
    """Rewrite a seed CSV with a fixed column order and Unix newlines."""
    path = SEEDS / f"{name}.csv"
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(columns)
        for row in df[columns].itertuples(index=False):
            writer.writerow(["" if pd.isna(v) else v for v in row])


def categories() -> list[str]:
    return read_seed("categories")["category"].tolist()


# --- pipeline actions ----------------------------------------------------


def new_statements() -> list[str]:
    """Statement CSVs on disk that the warehouse hasn't loaded yet.

    A file counts as new if no row in the warehouse came from it, or if
    it was modified after the last refresh (a re-downloaded export).
    Paths are relative to the statements root, matching source_file.
    """
    on_disk = {
        str(p.relative_to(STATEMENTS)): p.stat().st_mtime
        for p in STATEMENTS.glob("*/*.csv")
    }
    if not on_disk:
        return []
    if not db_exists():
        return sorted(on_disk)
    loaded = set(
        query("SELECT DISTINCT source_file FROM raw_bank.transactions")[
            "source_file"
        ]
    )
    built_at = DB_PATH.stat().st_mtime
    return sorted(
        path
        for path, mtime in on_disk.items()
        if path not in loaded or mtime > built_at
    )


def run_refresh(ingest: bool, on_step=None) -> RefreshResult:
    """Build on a copy and swap it in (see ingest/refresh.py)."""
    result = refresh(ingest=ingest, on_step=on_step)
    if result.ok:
        st.cache_data.clear()
    return result


def refresh_with_status(ingest: bool, success: str, on_failure=None) -> None:
    """Run a refresh behind a status box; rerun the app when it lands.

    On failure the live database is unchanged, `on_failure` (if given)
    runs -- e.g. to undo a seed edit -- and the log is shown.
    """
    with st.status("Refreshing…", expanded=False) as status:
        result = run_refresh(
            ingest, on_step=lambda label: status.update(label=f"{label}…")
        )
        if not result.ok:
            if on_failure:
                on_failure()
            status.update(label=result.summary, state="error", expanded=True)
            if result.log:
                st.code(result.log[-4000:], language=None)
            st.stop()
        status.update(label="Done", state="complete")
    st.session_state["flash"] = f"{success} · {result.summary}"
    st.rerun()
