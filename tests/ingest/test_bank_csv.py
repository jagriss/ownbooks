"""Unit tests for the bank CSV source parser.

Description: Exercises layout detection, row parsing, and transaction
    hashing in ingest.sources.bank_csv against the synthetic exports in
    tests/fixtures/statements and small temp files, so parsing
    regressions are caught without real financial data.
Usage: pixi run test
Parameters: none.
Returns: n/a (unittest module).
"""

import tempfile
import unittest
from pathlib import Path

from ingest.sources.bank_csv import (
    LAYOUT_COLUMNS,
    METADATA_COLUMNS,
    detect_layout,
    parse_statement,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "statements"


class DetectLayoutTest(unittest.TestCase):
    """Header-based layout detection."""

    def test_known_headers(self) -> None:
        cases = {
            "chase_checking": "Details,Posting Date,Description,Amount,"
            "Type,Balance,Check or Slip #",
            "chase_card": "Transaction Date,Post Date,Description,"
            "Category,Type,Amount,Memo",
            "amex": "Date,Description,Amount",
            # Amex extended export still detects as amex.
            "amex_extended": "Date,Description,Card Member,Account #,"
            "Amount,Extended Details,Reference,Category",
        }
        for expected, header in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(
                    detect_layout(header.split(",")),
                    expected.removesuffix("_extended"),
                )

    def test_unknown_header_raises(self) -> None:
        with self.assertRaises(ValueError):
            detect_layout(["When", "What", "How Much"])


class ParseStatementTest(unittest.TestCase):
    """Row parsing against the fixture exports."""

    def test_chase_checking_trailing_comma(self) -> None:
        path = next((FIXTURES / "chase_checking").glob("*.csv"))
        layout, rows = parse_statement(path, "chase_checking")
        self.assertEqual(layout, "chase_checking")
        self.assertTrue(rows)
        # The trailing comma's extra field must not leak in as a column.
        self.assertTrue(all(None not in row for row in rows))
        self.assertIn("posting_date", rows[0])
        self.assertIn("check_or_slip", rows[0])

    def test_same_day_duplicates_kept_distinct(self) -> None:
        path = next((FIXTURES / "chase_sapphire").glob("*.csv"))
        _, rows = parse_statement(path, "chase_sapphire")
        coffees = [
            row
            for row in rows
            if row["transaction_date"] == "05/11/2026"
            and "BLUE BOTTLE" in row["description"]
        ]
        self.assertEqual(len(coffees), 2)
        self.assertEqual({row["occurrence_n"] for row in coffees}, {1, 2})
        self.assertNotEqual(coffees[0]["txn_hash"], coffees[1]["txn_hash"])

    def test_overlapping_exports_hash_identically(self) -> None:
        files = sorted((FIXTURES / "amex_gold").glob("*.csv"))
        hashes = [
            {row["txn_hash"] for row in parse_statement(f, "amex_gold")[1]}
            for f in files
        ]
        # Both fixture files contain June; those rows must collide.
        self.assertEqual(len(hashes[0] & hashes[1]), 4)

    def test_hash_depends_on_account(self) -> None:
        path = next((FIXTURES / "amex_gold").glob("*.csv"))
        _, rows_a = parse_statement(path, "amex_gold")
        _, rows_b = parse_statement(path, "amex_platinum")
        self.assertNotEqual(rows_a[0]["txn_hash"], rows_b[0]["txn_hash"])

    def test_every_column_is_declared(self) -> None:
        # Raw tables freeze their columns, so a parsed column missing
        # from LAYOUT_COLUMNS would fail every load of that layout.
        for path in sorted(FIXTURES.glob("*/*.csv")):
            layout, rows = parse_statement(path, path.parent.name)
            declared = set(LAYOUT_COLUMNS[layout]) | set(METADATA_COLUMNS)
            with self.subTest(file=path.name):
                for row in rows:
                    self.assertLessEqual(set(row), declared)

    def test_source_file_is_relative(self) -> None:
        path = next((FIXTURES / "amex_gold").glob("*.csv"))
        _, rows = parse_statement(path, "amex_gold")
        # An absolute path would leak the home directory into the data.
        self.assertEqual(rows[0]["source_file"], f"amex_gold/{path.name}")

    def test_amount_normalized_and_bom_stripped(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "export.csv"
            path.write_text(
                '﻿Date,Description,Amount\n01/02/2026,X,"1,204.5"\n',
                encoding="utf-8",
            )
            layout, rows = parse_statement(path, "amex_gold")
        self.assertEqual(layout, "amex")
        self.assertEqual(rows[0]["amount"], "1204.50")


if __name__ == "__main__":
    unittest.main()
