#!/usr/bin/env python3
"""Check the published files against `schema.json` before they are committed.

The scheduled workflow runs this between the export and the commit, so a file
that stopped matching its own published schema never reaches the history. It is
also the script to run after editing anything by hand.

Exits non-zero and prints every problem it found, rather than stopping at the
first one — a broken export usually breaks more than one row.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((REPO / "schema.json").read_text(encoding="utf-8"))

FIELDS = {field["name"]: field for field in SCHEMA["fields"]}
ORDER = [field["name"] for field in SCHEMA["fields"]]
KEY = SCHEMA["primaryKey"]

problems: list[str] = []


def fail(where: str, message: str) -> None:
    problems.append(f"{where}: {message}")


def check_value(where: str, field: dict, value: str) -> object | None:
    name = field["name"]
    constraints = field.get("constraints", {})

    if value == "":
        if constraints.get("required"):
            fail(where, f"{name} is required but empty")
        return None

    if field["type"] == "datetime":
        try:
            return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            fail(where, f"{name} is not an ISO 8601 UTC timestamp: {value!r}")
            return None

    if field["type"] == "number":
        try:
            number = float(value)
        except ValueError:
            fail(where, f"{name} is not a number: {value!r}")
            return None
        minimum = constraints.get("minimum")
        if minimum is not None and number < minimum:
            fail(where, f"{name} below the allowed minimum: {number}")
        if not re.fullmatch(r"-?\d+\.\d{2}", value):
            fail(where, f"{name} is not formatted with two decimals: {value!r}")
        return number

    enum = constraints.get("enum")
    if enum and value not in enum:
        fail(where, f"{name} outside the allowed values: {value!r}")
    pattern = constraints.get("pattern")
    if pattern and not re.fullmatch(pattern, value):
        fail(where, f"{name} does not match {pattern}: {value!r}")
    return value


def check_file(
    path: Path,
    expect_market: str | None,
    expect_month: str | None,
    *,
    chronological: bool,
) -> int:
    """Validate one file.

    `chronological` is off for `latest.csv`: that file holds one row per model
    sorted by market and name, so its timestamps are legitimately out of order.
    """
    relative = path.relative_to(REPO)
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ORDER:
            fail(str(relative), f"header mismatch: {reader.fieldnames}")
            return 0

        seen: set[tuple] = set()
        previous: datetime | None = None
        count = 0

        for line, row in enumerate(reader, start=2):
            where = f"{relative}:{line}"
            count += 1
            values = {
                name: check_value(where, FIELDS[name], row[name]) for name in ORDER
            }

            key = tuple(row[name] for name in KEY)
            if key in seen:
                fail(where, f"duplicate primary key {key}")
            seen.add(key)

            if expect_market and row["market"] != expect_market:
                fail(where, f"market {row['market']} in a {expect_market} file")
            if expect_month and not row["observed_at"].startswith(expect_month):
                fail(where, f"observation dated outside {expect_month}")

            stamp = values["observed_at"]
            if chronological and isinstance(stamp, datetime):
                if previous and stamp < previous:
                    fail(where, "rows are not sorted by observed_at")
                previous = stamp

    return count


def main() -> None:
    total = 0

    latest = REPO / "latest.csv"
    if not latest.exists():
        fail("latest.csv", "missing")
    else:
        check_file(latest, None, None, chronological=False)

    files = sorted((REPO / "data").rglob("*.csv"))
    if not files:
        fail("data/", "no CSV file found")

    for path in files:
        market = path.parent.name.upper()
        total += check_file(path, market, path.stem, chronological=True)

    stats_path = REPO / "stats.json"
    if stats_path.exists():
        stats = json.loads(stats_path.read_text(encoding="utf-8"))
        if stats.get("observations") != total:
            fail(
                "stats.json",
                f"announces {stats.get('observations')} observations, files hold {total}",
            )

    package = REPO / "datapackage.json"
    if package.exists():
        declared = {
            resource["path"]
            for resource in json.loads(package.read_text(encoding="utf-8"))["resources"]
        }
        actual = {str(path.relative_to(REPO)) for path in files} | {"latest.csv"}
        for missing in sorted(actual - declared):
            fail("datapackage.json", f"{missing} is not declared")
        for extra in sorted(declared - actual):
            fail("datapackage.json", f"{extra} is declared but absent")

    if problems:
        print(f"{len(problems)} problem(s) found:", file=sys.stderr)
        for problem in problems[:50]:
            print(f"  {problem}", file=sys.stderr)
        if len(problems) > 50:
            print(f"  … and {len(problems) - 50} more", file=sys.stderr)
        sys.exit(1)

    print(f"Dataset valid — {total} observations across {len(files)} files")


if __name__ == "__main__":
    main()
