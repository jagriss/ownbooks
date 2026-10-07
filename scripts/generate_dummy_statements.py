"""Generate a year of realistic dummy Chase and Amex CSV exports.

Description: Writes synthetic statement exports for the three accounts in
    transform/seeds/accounts.csv (chase_checking, chase_sapphire,
    amex_gold) in each bank's real export format, so the full pipeline
    can be exercised without real financial data. Seeded, so output is
    reproducible.

    What it deliberately includes, to exercise the pipeline:
    - Chase checking's trailing-comma rows and running balance column.
    - Amex's *extended* export: issuer-signed amounts, padded city/state
      descriptions, quoted multi-line "Extended Details" fields.
    - Quarterly export files whose date windows overlap (dedup).
    - Card payments that pay each card's prior-month balance from
      checking (transfer pairing).
    - Same-day identical purchases, refunds, seasonal utility bills,
      fixed-price subscriptions, and merchants with no rule yet.
Usage: pixi run dummy-data   (then: pixi run elt && pixi run todo)
Parameters: --out DIR (default $FINANCE_STATEMENTS_ROOT or
    data/statements), --months N (default 12), --seed N (default 7).
Returns: exit code 0; prints the files written.

Notes
-----
Only files named `dummy_*.csv` are ever written or deleted, so this is
safe to run against a statements folder that also holds real exports --
though mixing the two makes the marts meaningless.
"""

import argparse
import csv
import hashlib
import os
import random
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

# Merchant pools: (description as the bank prints it, low, high).
# Chase card descriptions follow Chase's style; Amex's are padded out
# with city and state, as Amex exports them.
CHASE_GROCERIES = [("WHOLEFDS MKT 10234", 38, 165), ("SAFEWAY #1711", 22, 95)]
CHASE_COFFEE = [
    ("SQ *BLUE BOTTLE COFFEE", 5.5, 9.0),
    ("SQ *SIGHTGLASS COFFEE", 4.75, 8.5),
    ("STARBUCKS STORE 05521", 4.95, 11.4),
]
CHASE_DINING = [
    ("TST* ZUNI CAFE", 48, 160),
    ("TST* NOPA", 55, 140),
    ("UBER   *EATS", 22, 58),
    ("DOORDASH*THAI TIME", 24, 47),
    ("CHIPOTLE 2291", 11, 19),
]
CHASE_RIDES = [("UBER   *TRIP", 9, 42), ("LYFT   *RIDE SUN 9PM", 8, 36)]
CHASE_GAS = [("SHELL OIL 57444190012", 34, 72), ("CHEVRON 0091422", 31, 68)]
CHASE_OTHER = [
    ("CVS/PHARMACY #09812", 6, 48),
    ("TARGET        00028432", 18, 140),
    ("WALGREENS #3381", 5, 31),
    ("SFMTA METER PAYMENT", 2.5, 9),
]
AMEX_GROCERIES = [
    ("TRADER JOE S #123      SAN FRANCISCO       CA", 25, 110),
    ("COSTCO WHSE #0144      SAN FRANCISCO       CA", 90, 310),
]
AMEX_SHOPPING = [
    ("AMAZON MKTPLACE PMTS   AMZN.COM/BILL       WA", 9, 140),
    ("AMAZON.COM*2K4LP91     AMZN.COM/BILL       WA", 12, 85),
    ("ETSY.COM - LUNACERAMIC BROOKLYN            NY", 18, 75),
    ("THE HOME DEPOT #0645   SAN FRANCISCO       CA", 14, 220),
]
AMEX_DINING = [
    ("CHEZ PANISSE           BERKELEY            CA", 95, 240),
    ("TARTINE BAKERY         SAN FRANCISCO       CA", 12, 38),
    ("STATE BIRD PROVISIONS  SAN FRANCISCO       CA", 80, 210),
]
AMEX_TRAVEL = [
    ("DELTA AIR LINES        ATLANTA             GA", 180, 640),
    ("MARRIOTT HOTELS        BETHESDA            MD", 160, 520),
    ("AIRBNB * HMX2K9QW      SAN FRANCISCO       CA", 210, 780),
]


@dataclass
class Txn:
    """One generated transaction, signed outflow-negative."""

    day: date
    description: str
    amount: float
    kind: str = "Sale"  # Chase card "Type" / checking type hint
    category: str = ""  # bank's own category, where the bank has one


def _money(rng: random.Random, low: float, high: float) -> float:
    return round(rng.uniform(low, high), 2)


def _month_starts(end: date, months: int) -> list[date]:
    first = date(end.year, end.month, 1)
    starts = []
    for _ in range(months):
        starts.append(first)
        first = (first - timedelta(days=1)).replace(day=1)
    return sorted(starts)


def _days_in(month: date) -> int:
    nxt = (month + timedelta(days=32)).replace(day=1)
    return (nxt - month).days


def _random_day(rng: random.Random, month: date, end: date) -> date | None:
    day = month + timedelta(days=rng.randrange(_days_in(month)))
    return day if day <= end else None


def _sprinkle(rng, txns, month, end, pool, per_month, category, sign=-1):
    """Add a random number of purchases from `pool` within `month`."""
    for _ in range(rng.randint(*per_month)):
        day = _random_day(rng, month, end)
        if day is None:
            continue
        desc, low, high = rng.choice(pool)
        txns.append(
            Txn(day, desc, sign * _money(rng, low, high), "Sale", category)
        )


def generate_sapphire(rng, months, end) -> list[Txn]:
    """Chase Sapphire purchases (negative), returns (positive)."""
    txns: list[Txn] = []
    for month in months:
        _sprinkle(rng, txns, month, end, CHASE_GROCERIES, (3, 6), "Groceries")
        _sprinkle(rng, txns, month, end, CHASE_COFFEE, (6, 12), "Food & Drink")
        _sprinkle(rng, txns, month, end, CHASE_DINING, (4, 8), "Food & Drink")
        _sprinkle(rng, txns, month, end, CHASE_RIDES, (2, 6), "Travel")
        _sprinkle(rng, txns, month, end, CHASE_GAS, (1, 3), "Gas")
        _sprinkle(rng, txns, month, end, CHASE_OTHER, (2, 5), "Shopping")
        # Fixed-price subscriptions on fixed days.
        for day, desc, amount, cat in (
            (3, "NETFLIX.COM", 15.49, "Entertainment"),
            (9, "SPOTIFY USA", 11.99, "Entertainment"),
            (14, "OPENAI *CHATGPT SUBSCR", 20.00, "Shopping"),
            (21, "EQUINOX #142", 245.00, "Health & Wellness"),
        ):
            charge_day = month.replace(day=day)
            if charge_day <= end:
                txns.append(Txn(charge_day, desc, -amount, "Sale", cat))
        # A same-day double coffee most months (must stay two rows).
        coffee_day = month.replace(day=11)
        if coffee_day <= end and rng.random() < 0.7:
            for _ in range(2):
                txns.append(
                    Txn(
                        coffee_day,
                        "SQ *BLUE BOTTLE COFFEE",
                        -6.50,
                        "Sale",
                        "Food & Drink",
                    )
                )
        # An occasional return.
        if rng.random() < 0.35:
            day = _random_day(rng, month, end)
            if day:
                txns.append(
                    Txn(
                        day,
                        "TARGET        00028432",
                        _money(rng, 12, 60),
                        "Return",
                        "Shopping",
                    )
                )
    return txns


def generate_amex(rng, months, end) -> list[Txn]:
    """Amex Gold purchases (negative here; flipped when written)."""
    txns: list[Txn] = []
    cat_map = {
        "groceries": "Merchandise & Supplies-Groceries",
        "shopping": "Merchandise & Supplies-Internet Purchase",
        "dining": "Restaurant-Restaurant",
        "travel": "Travel-Airline",
    }
    for month in months:
        _sprinkle(
            rng, txns, month, end, AMEX_GROCERIES, (2, 5), cat_map["groceries"]
        )
        _sprinkle(
            rng, txns, month, end, AMEX_SHOPPING, (2, 6), cat_map["shopping"]
        )
        _sprinkle(rng, txns, month, end, AMEX_DINING, (1, 3), cat_map["dining"])
        if rng.random() < 0.3:
            _sprinkle(
                rng, txns, month, end, AMEX_TRAVEL, (1, 2), cat_map["travel"]
            )
        for day, desc, amount, cat in (
            (
                10,
                "NYTIMES*NYTDIGITAL     NEW YORK            NY",
                4.00,
                "Merchandise & Supplies-Internet Purchase",
            ),
            (
                17,
                "APPLE.COM/BILL         CUPERTINO           CA",
                2.99,
                "Merchandise & Supplies-Internet Purchase",
            ),
        ):
            charge_day = month.replace(day=day)
            if charge_day <= end:
                txns.append(Txn(charge_day, desc, -amount, "Sale", cat))
        # Amex dining credit: a statement credit, issuer-signed negative.
        credit_day = month.replace(day=28)
        if credit_day <= end:
            txns.append(
                Txn(
                    credit_day,
                    "DINING CREDIT          AMEX GOLD",
                    10.00,
                    "Credit",
                    "Fees & Adjustments-Fees & Adjustments",
                )
            )
    return txns


def _monthly_balances(txns: list[Txn]) -> dict[date, float]:
    """Net card spend per calendar month (positive = owed)."""
    owed: dict[date, float] = defaultdict(float)
    for txn in txns:
        owed[txn.day.replace(day=1)] -= txn.amount
    return owed


def generate_checking(rng, months, end, sapphire, amex) -> list[Txn]:
    """Chase checking: pay, rent, bills, and the two card payments.

    Card payments are appended to the card transaction lists too, so
    each payment has its matching other side.
    """
    txns: list[Txn] = []
    # Biweekly payroll on Fridays.
    payday = months[0] + timedelta(days=(4 - months[0].weekday()) % 7)
    while payday <= end:
        txns.append(
            Txn(
                payday,
                "ACME CORP PAYROLL PPD ID: 9000000001",
                2450.00,
                "ACH_CREDIT",
            )
        )
        payday += timedelta(days=14)

    sapphire_owed = _monthly_balances(sapphire)
    amex_owed = _monthly_balances(amex)
    for i, month in enumerate(months):

        def on(day: int) -> date | None:
            d = month.replace(day=min(day, _days_in(month)))
            return d if d <= end else None

        if d := on(1):
            ref = "".join(
                rng.choices("ABCDEFGHJKLMNPQRSTUVWXYZ0123456789", k=8)
            )
            txns.append(
                Txn(
                    d,
                    f"ZELLE PAYMENT TO LANDLORD LLC JPM99{ref}",
                    -1500.00,
                    "QUICKPAY_DEBIT",
                )
            )
        if d := on(12):
            # PG&E: higher in winter (heating) and summer (AC).
            seasonal = {12: 60, 1: 70, 2: 55, 7: 35, 8: 40}.get(month.month, 0)
            txns.append(
                Txn(
                    d,
                    "PGANDE WEB ONLINE PPD ID: 9000000002",
                    -(_money(rng, 68, 92) + seasonal),
                    "ACH_DEBIT",
                )
            )
        if d := on(16):
            txns.append(
                Txn(
                    d,
                    "COMCAST CABLE COMM PPD ID: 0000004811",
                    -79.99,
                    "ACH_DEBIT",
                )
            )
        if d := on(28):
            txns.append(
                Txn(
                    d,
                    "INTEREST PAYMENT",
                    round(rng.uniform(0.4, 1.9), 2),
                    "MISC_CREDIT",
                )
            )
        if rng.random() < 0.6 and (d := _random_day(rng, month, end)):
            txns.append(
                Txn(
                    d,
                    f"ATM WITHDRAWAL 00{rng.randint(1000, 9999)} {d:%m/%d} MAIN ST",
                    -float(rng.choice((40, 60, 80, 100))),
                    "ATM",
                )
            )
        if rng.random() < 0.5 and (d := _random_day(rng, month, end)):
            txns.append(
                Txn(
                    d,
                    f"VENMO PAYMENT 10{rng.randint(10**8, 10**9 - 1)} WEB ID: 3264681992",
                    -_money(rng, 15, 120),
                    "ACH_DEBIT",
                )
            )

        # Pay last month's card balances: Amex autopay on the 19th (it
        # lands in checking the next day), Chase on the 25th.
        if i == 0:
            continue
        prior = months[i - 1]
        if (d := on(19)) and amex_owed.get(prior, 0) > 0:
            amount = round(amex_owed[prior], 2)
            amex.append(
                Txn(d, "AUTOPAY PAYMENT - THANK YOU", amount, "Payment")
            )
            txns.append(
                Txn(
                    d + timedelta(days=1),
                    f"AMERICAN EXPRESS ACH PMT M{rng.randint(1000, 9999)} WEB ID: 2005032111",
                    -amount,
                    "ACH_DEBIT",
                )
            )
        if (d := on(25)) and sapphire_owed.get(prior, 0) > 0:
            amount = round(sapphire_owed[prior], 2)
            sapphire.append(
                Txn(d, "Payment Thank You-Mobile", amount, "Payment")
            )
            txns.append(
                Txn(
                    d,
                    f"Payment to Chase card ending in 4321 {d:%m/%d}",
                    -amount,
                    "LOAN_PMT",
                )
            )
    return txns


def _windows(
    months: list[date], end: date, overlap_days: int
) -> list[tuple[date, date]]:
    """Quarterly export windows, each starting `overlap_days` early."""
    windows = []
    for i in range(0, len(months), 3):
        start = months[i]
        stop_month = months[min(i + 2, len(months) - 1)]
        stop = min(stop_month.replace(day=_days_in(stop_month)), end)
        windows.append(
            (start - timedelta(days=overlap_days) if i else start, stop)
        )
    return windows


def write_chase_checking(path: Path, txns: list[Txn], opening: float) -> None:
    rows = sorted(txns, key=lambda t: t.day)
    balance = opening
    with_balance = []
    for t in rows:
        balance += t.amount
        with_balance.append((t, balance))
    with path.open("w", newline="") as f:
        f.write(
            "Details,Posting Date,Description,Amount,Type,Balance,Check or Slip #\n"
        )
        for t, bal in reversed(with_balance):  # Chase lists newest first
            details = "CREDIT" if t.amount > 0 else "DEBIT"
            # Real exports end each row with a comma the header lacks.
            f.write(
                f'{details},{t.day:%m/%d/%Y},"{t.description}",{t.amount:.2f},{t.kind},{bal:.2f},,\n'
            )


def write_chase_card(path: Path, txns: list[Txn]) -> None:
    with path.open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(
            [
                "Transaction Date",
                "Post Date",
                "Description",
                "Category",
                "Type",
                "Amount",
                "Memo",
            ]
        )
        for t in sorted(txns, key=lambda t: t.day, reverse=True):
            post = t.day + timedelta(days=0 if t.kind == "Payment" else 1)
            w.writerow(
                [
                    f"{t.day:%m/%d/%Y}",
                    f"{post:%m/%d/%Y}",
                    t.description,
                    t.category,
                    t.kind,
                    f"{t.amount:.2f}",
                    "",
                ]
            )


def write_amex(path: Path, txns: list[Txn]) -> None:
    header = [
        "Date",
        "Description",
        "Card Member",
        "Account #",
        "Amount",
        "Extended Details",
        "Appears On Your Statement As",
        "Address",
        "City/State",
        "Zip Code",
        "Country",
        "Reference",
        "Category",
    ]
    with path.open("w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        for t in sorted(txns, key=lambda t: t.day, reverse=True):
            merchant, *place = [
                p for p in t.description.split("  ") if p.strip()
            ]
            city_state = " ".join(p.strip() for p in place)
            # Amex signs from its own side: charges positive.
            amount = -t.amount
            # Reference must be identical for a transaction appearing in
            # two overlapping exports, so derive it from the transaction.
            digest = hashlib.sha256(
                f"{t.day}{t.description}{t.amount}".encode()
            )
            ref = int(digest.hexdigest(), 16) % 10**18
            w.writerow(
                [
                    f"{t.day:%m/%d/%Y}",
                    t.description,
                    "CARD MEMBER",
                    "-41007",
                    f"{amount:.2f}",
                    # Real extended details are multi-line, quoted fields.
                    f"{merchant.strip()}\n{city_state}\nDescription : {t.kind.upper()}",
                    t.description,
                    "",
                    city_state,
                    "",
                    "UNITED STATES",
                    f"'{ref:018d}'",
                    t.category,
                ]
            )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        default=os.environ.get("FINANCE_STATEMENTS_ROOT", "data/statements"),
    )
    parser.add_argument("--months", type=int, default=12)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    end = date(2026, 9, 30)
    months = _month_starts(end, args.months)

    sapphire = generate_sapphire(rng, months, end)
    amex = generate_amex(rng, months, end)
    checking = generate_checking(rng, months, end, sapphire, amex)

    out = Path(args.out)
    for account in ("chase_checking", "chase_sapphire", "amex_gold"):
        folder = out / account
        folder.mkdir(parents=True, exist_ok=True)
        for old in folder.glob("dummy_*.csv"):
            old.unlink()

    written = []
    # Chase: one export per quarter, windows touching. Amex: quarterly
    # with a 14-day overlap, so the loader's dedup gets exercised.
    for start, stop in _windows(months, end, overlap_days=0):
        part = [t for t in checking if start <= t.day <= stop]
        opening = 8000 + sum(t.amount for t in checking if t.day < start)
        p = (
            out
            / "chase_checking"
            / f"dummy_Chase1234_Activity_{start:%Y%m%d}_{stop:%Y%m%d}.csv"
        )
        write_chase_checking(p, part, opening)
        written.append(p)
        p = (
            out
            / "chase_sapphire"
            / f"dummy_Chase4321_Activity{start:%Y%m%d}_{stop:%Y%m%d}.csv"
        )
        write_chase_card(p, [t for t in sapphire if start <= t.day <= stop])
        written.append(p)
    for start, stop in _windows(months, end, overlap_days=14):
        p = (
            out
            / "amex_gold"
            / f"dummy_amex_activity_{start:%Y%m%d}_{stop:%Y%m%d}.csv"
        )
        write_amex(p, [t for t in amex if start <= t.day <= stop])
        written.append(p)

    for p in written:
        print(p)
    print(
        f"{len(checking)} checking, {len(sapphire)} Sapphire, {len(amex)} Amex "
        f"transactions, {months[0]:%Y-%m} to {end:%Y-%m}"
    )


if __name__ == "__main__":
    main()
