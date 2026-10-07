#!/usr/bin/env python3
"""Block financial data and personal identifiers from being committed.

Description: Layer 2 of the repo's data-leak protection (.gitignore is
    layer 1). Runs as the git pre-commit hook via .githooks/pre-commit
    and checks staged files; .gitignore can't stop `git add -f`, this
    can. Stdlib only, so it runs without the pixi environment.

    Blocks a commit when a staged file:
    - lives under data/ (other than data/statements/.gitkeep);
    - has a statement, export, or warehouse extension (.duckdb, .pdf,
      .ofx, .xlsx, .parquet, ...);
    - is a CSV outside transform/seeds/ and tests/fixtures/statements/;
    - is a fixture CSV larger than FIXTURE_MAX_BYTES (a real export
      copied in as a "fixture" is the most likely accident);
    - contains a Luhn-valid 13-19 digit number (a card number) or an
      email address other than a no-reply / example one.
Usage: pixi run check-private        (every tracked file)
       pixi run install-hooks        (run on each commit from now on)
Parameters: --all checks every tracked file instead of staged ones.
Returns: exit code 0 if clean, 1 with a report if anything is blocked.
"""

import re
import subprocess
import sys
from pathlib import PurePosixPath

ALLOWED_DATA_PATHS = {"data/statements/.gitkeep"}
BLOCKED_SUFFIXES = {
    ".duckdb", ".wal", ".db", ".sqlite", ".sqlite3", ".parquet",
    ".pdf", ".ofx", ".qfx", ".qbo", ".xls", ".xlsx", ".tsv",
}  # fmt: skip
ALLOWED_CSV_DIRS = ("transform/seeds/", "tests/fixtures/statements/")
FIXTURE_MAX_BYTES = 8_000
# Generated files full of hashes; scanning them only yields noise.
SKIP_CONTENT_SCAN = {"pixi.lock"}

# Standalone digit runs only: not inside hashes, versions, or IDs.
DIGIT_RUN = re.compile(r"(?<![\w.])\d{13,19}(?![\w.])")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
ALLOWED_EMAIL = re.compile(
    r"(noreply|no-reply)@|users\.noreply\.github\.com$|@example\.(com|org)$",
    re.IGNORECASE,
)


def _git(*args: str) -> bytes:
    return subprocess.run(
        ["git", *args], check=True, capture_output=True
    ).stdout


def _luhn_valid(number: str) -> bool:
    """True if `number` passes the Luhn checksum card numbers use."""
    total = 0
    for i, ch in enumerate(reversed(number)):
        digit = int(ch)
        if i % 2:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
    return total % 10 == 0


def path_problems(path: str, size: int) -> list[str]:
    """Reasons a path may not be committed, judged by name and size."""
    p = PurePosixPath(path)
    suffix = p.suffix.lower()
    if path.startswith("data/") and path not in ALLOWED_DATA_PATHS:
        return ["under data/ (statements and warehouse live here)"]
    if suffix in BLOCKED_SUFFIXES:
        return [f"{suffix} files are statement/warehouse formats"]
    if suffix == ".csv":
        if not path.startswith(ALLOWED_CSV_DIRS):
            return ["CSV outside transform/seeds/ and tests/fixtures/"]
        if path.startswith("tests/fixtures/") and size > FIXTURE_MAX_BYTES:
            return [
                f"fixture is {size:,} bytes (limit {FIXTURE_MAX_BYTES:,}); "
                "real exports are bigger than hand-made fixtures"
            ]
    return []


def content_problems(text: str) -> list[str]:
    """Reasons file content may not be committed."""
    problems = []
    for match in DIGIT_RUN.finditer(text):
        if _luhn_valid(match.group()):
            line = text.count("\n", 0, match.start()) + 1
            problems.append(f"line {line}: looks like a card number")
    for match in EMAIL.finditer(text):
        if not ALLOWED_EMAIL.search(match.group()):
            line = text.count("\n", 0, match.start()) + 1
            problems.append(f"line {line}: email address {match.group()}")
    return problems


def _files(check_all: bool) -> list[tuple[str, bytes]]:
    """(path, content) for staged files, or for every tracked file."""
    if check_all:
        paths = _git("ls-files", "-z").decode().split("\0")
        return [(p, open(p, "rb").read()) for p in paths if p]
    paths = _git(
        "diff", "--cached", "--name-only", "-z", "--diff-filter=ACMR"
    ).decode()
    # Read the staged blob, not the working copy: that's what commits.
    return [(p, _git("show", f":{p}")) for p in paths.split("\0") if p]


def main() -> int:
    report = []
    for path, blob in _files("--all" in sys.argv):
        problems = path_problems(path, len(blob))
        binary = b"\0" in blob[:8000]
        if not problems and not binary and path not in SKIP_CONTENT_SCAN:
            problems = content_problems(blob.decode("utf-8", "replace"))
        report += [f"  {path}: {problem}" for problem in problems]
    if report:
        print("Blocked: possible financial or personal data.", file=sys.stderr)
        print("\n".join(report), file=sys.stderr)
        print(
            "\nUnstage with `git rm --cached <path>` (keeps the file on disk). If a match is a "
            "false positive, change the value rather than bypassing the "
            "check.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
