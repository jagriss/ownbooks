"""Rebuild the warehouse on a copy, then swap it in atomically.

Description: The only supported way to change data/finance.duckdb.
    DuckDB allows one writing process per file, and a writer can't open
    the file while anyone else has it open -- so building in place
    collides with the app, `pixi run sql`, or the DuckDB UI. Instead:

    1. copy the live file to data/.build/finance.duckdb (a byte copy;
       it needs no DuckDB lock, so open readers don't block it). Same
       file name in another folder, not finance.build.duckdb: DuckDB
       names the catalog after the file stem, and dbt writes that name
       into every view, so a different stem would break the views once
       the file is renamed back;
    2. run ingestion and/or `dbt build` against the copy;
    3. if every step succeeds (dbt tests included), os.replace() the
       copy over the live file -- atomic, so readers see either the old
       database or the new one, never a half-built one.

    A failed build leaves the live database untouched. A file lock
    (data/.refresh.lock) keeps two refreshes from running at once.
Usage: pixi run refresh            (ingest new statements + dbt build)
       pixi run refresh --models   (dbt build only, e.g. after editing
                                    seeds/merchant_rules.csv)
       from ingest.refresh import refresh   (the app's buttons)
Returns: exit code 0 if the new database was swapped in, 1 if not.
"""

import fcntl
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRANSFORM = ROOT / "transform"

# Nothing leaves the machine at runtime: dlt and dbt send anonymous usage
# telemetry by default, and dbt Fusion checks a CDN for updates each run.
# scripts/activate-env.sh sets these for pixi tasks; they're applied here
# too so the app's refreshes stay offline however it was launched.
OFFLINE_ENV = {
    "RUNTIME__DLTHUB_TELEMETRY": "false",
    "DO_NOT_TRACK": "1",
    "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    "DBT_DISABLE_VERSION_CHECK": "1",
}


def live_path() -> Path:
    return Path(
        os.environ.get("FINANCE_DUCKDB_PATH", ROOT / "data" / "finance.duckdb")
    )


@dataclass
class RefreshResult:
    ok: bool
    summary: str
    log: str = ""
    steps: list[str] = field(default_factory=list)


def _wal(path: Path) -> Path:
    return path.with_name(path.name + ".wal")


def _steps(ingest: bool) -> list[tuple[str, list[str]]]:
    steps = []
    if ingest:
        steps.append(
            (
                "Loading statements",
                [sys.executable, "-m", "ingest.pipelines.run_bank_csv"],
            )
        )
    steps.append(
        (
            "Building models",
            [
                "dbt",
                "build",
                "--project-dir",
                str(TRANSFORM),
                "--profiles-dir",
                str(TRANSFORM),
            ],
        )
    )
    return steps


def refresh(
    ingest: bool = True, stream: bool = False, on_step=None
) -> RefreshResult:
    """Build a new warehouse on a copy and swap it in if it passes.

    Parameters
    ----------
    ingest : bool
        Load statements before building. False runs dbt only.
    stream : bool
        Print subprocess output live (CLI) instead of capturing it.
    on_step : callable, optional
        Called with each step's label as it starts (the app's status).

    Returns
    -------
    RefreshResult
    """
    live = live_path()
    build = live.parent / ".build" / live.name
    build.parent.mkdir(parents=True, exist_ok=True)

    with open(live.parent / ".refresh.lock", "w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return RefreshResult(False, "A refresh is already running.")

        for stale in (build, _wal(build)):
            stale.unlink(missing_ok=True)
        if live.exists():
            shutil.copy2(live, build)
            if _wal(live).exists():
                shutil.copy2(_wal(live), _wal(build))

        env = {**OFFLINE_ENV, **os.environ}
        env["FINANCE_DUCKDB_PATH"] = str(build)
        # dlt keeps pipeline state in a local working dir. Start each
        # build with an empty one so state is restored from the copy
        # being built, never from a previous build that was discarded.
        dlt_dir = live.parent / ".dlt"
        shutil.rmtree(dlt_dir, ignore_errors=True)
        env["DLT_DATA_DIR"] = str(dlt_dir)

        logs, done = [], []
        for label, cmd in _steps(ingest):
            if on_step:
                on_step(label)
            if stream:
                print(f"\n==> {label}", flush=True)
            proc = subprocess.run(
                cmd, cwd=ROOT, env=env, text=True,
                capture_output=not stream,
            )  # fmt: skip
            if not stream:
                logs.append(f"==> {label}\n{proc.stdout}{proc.stderr}")
            if proc.returncode != 0:
                build.unlink(missing_ok=True)
                _wal(build).unlink(missing_ok=True)
                return RefreshResult(
                    False,
                    f"{label} failed; the live database was not changed.",
                    "\n".join(logs),
                    done,
                )
            done.append(label)

        # Swap. The build was closed cleanly, so it should have no WAL;
        # carry one over if it does, and never leave a stale live WAL.
        if _wal(build).exists():
            os.replace(_wal(build), _wal(live))
        else:
            _wal(live).unlink(missing_ok=True)
        os.replace(build, live)

    log = "\n".join(logs)
    summary = next(
        (l.strip() for l in reversed(log.splitlines()) if "Summary:" in l),
        "Done",
    )
    return RefreshResult(True, summary, log, done)


def main() -> int:
    result = refresh(ingest="--models" not in sys.argv, stream=True)
    print(f"\n{'✔' if result.ok else '✘'} {result.summary}")
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main())
