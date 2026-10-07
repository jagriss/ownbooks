"""Entry point that loads bank CSV exports into DuckDB.

Description: Runs `bank_csv_source` through a dlt pipeline into the
    local DuckDB warehouse. Re-running over the same files is a no-op
    thanks to the merge on `txn_hash`, so exports can stay in place and
    overlapping date ranges are fine.
Usage: pixi run ingest
Parameters: none (configuration comes from environment variables set by
    pixi.toml's [activation.env], or from a local .env override).
Returns: exit code 0 on success; a non-zero dlt/Python traceback on
    failure.
"""

import os

import dlt

from ingest.sources.bank_csv import bank_csv_source


def build_pipeline() -> dlt.Pipeline:
    """Construct the dlt pipeline targeting the project's DuckDB file.

    Returns
    -------
    dlt.Pipeline
        Configured pipeline writing to the `raw_bank` dataset.
    """
    duckdb_path = os.environ.get("FINANCE_DUCKDB_PATH", "data/finance.duckdb")
    return dlt.pipeline(
        pipeline_name="bank_csv",
        destination=dlt.destinations.duckdb(duckdb_path),
        dataset_name="raw_bank",
    )


def main() -> None:
    """Run the statement load and print the dlt load summary."""
    pipeline = build_pipeline()
    load_info = pipeline.run(bank_csv_source())
    print(load_info)


if __name__ == "__main__":
    main()
