#!/usr/bin/env python3
"""Export the Price Radar observations to the CSV files of this repository.

The script is deliberately dependency-free: it talks to the PostgREST endpoint
with the standard library only, so the scheduled workflow needs no lockfile and
no install step.

Two properties matter more than anything else here.

**The output is deterministic.** Rows are sorted, prices are formatted with a
fixed number of decimals, and the newline is fixed. Running the export twice on
unchanged data produces byte-identical files, which is what lets the workflow
commit only when a new observation actually landed. Without that, the history
would fill with empty commits and stop being readable.

**The export is append-only in practice.** It rewrites whole month files rather
than appending lines, because a rewrite is the only way to stay deterministic;
but past months never change, so git stores one diff per day at most.
"""

from __future__ import annotations

import csv
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DATA = REPO / "data"

TABLE = "product_prices"
# Only the columns this dataset publishes. See README, "What is not included".
COLUMNS = "scraped_at,market,model,model_slug,price,currency,price_new"
PAGE_SIZE = 1000

MARKETS = ("FR", "US", "DE", "ES")

FIELDNAMES = [
    "observed_at",
    "market",
    "model_id",
    "model",
    "price",
    "currency",
    "reference_new_price",
]


def env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        sys.exit(
            f"Missing environment variable {name}. "
            "See SETUP.md for the two values this script expects."
        )
    return value


def fetch_all(base_url: str, key: str) -> list[dict]:
    """Read every observation, page by page.

    PostgREST caps a response at a fixed number of rows, so the range header is
    walked until a short page comes back. The order is set server-side on
    (scraped_at, market, model) so pagination is stable: without a total order,
    a row can be skipped or repeated between two pages.
    """
    rows: list[dict] = []
    offset = 0
    query = urllib.parse.urlencode(
        {
            "select": COLUMNS,
            "order": "scraped_at.asc,market.asc,model.asc",
        }
    )
    while True:
        request = urllib.request.Request(
            f"{base_url}/rest/v1/{TABLE}?{query}",
            headers={
                "apikey": key,
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
                "Range-Unit": "items",
                "Range": f"{offset}-{offset + PAGE_SIZE - 1}",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                page = json.load(response)
        except urllib.error.HTTPError as error:
            sys.exit(f"HTTP {error.code} from PostgREST: {error.read()[:400]!r}")
        except urllib.error.URLError as error:
            sys.exit(f"Cannot reach {base_url}: {error.reason}")

        rows.extend(page)
        if len(page) < PAGE_SIZE:
            return rows
        offset += PAGE_SIZE


def money(value) -> str:
    """Two decimals, always.

    The source mixes integers and decimals — 699 and 699.99 describe the same
    kind of amount. A fixed format keeps the column parseable and keeps the
    output stable between two runs.
    """
    if value is None or value == "":
        return ""
    return f"{float(value):.2f}"


def normalise(row: dict) -> dict | None:
    observed_at = row.get("scraped_at")
    market = row.get("market")
    model = row.get("model")
    price = row.get("price")
    if not observed_at or not market or not model or price is None:
        return None
    if market not in MARKETS:
        return None

    # Second precision in UTC: the collector's microseconds carry no meaning and
    # would only add noise to the diffs.
    stamp = datetime.fromisoformat(observed_at).astimezone(timezone.utc)

    return {
        "observed_at": stamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "market": market,
        "model_id": row.get("model_slug") or "",
        "model": model,
        "price": money(price),
        "currency": row.get("currency") or "",
        "reference_new_price": money(row.get("price_new")),
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def write_datapackage(files: list[tuple[str, str]], stats: dict) -> None:
    """Frictionless descriptor listing every published file.

    It is generated rather than hand-written so that a new month, or a new
    market, cannot silently fall out of the description. Data catalogues and
    validators read this file first.

    `version` and `created` follow the **data**, not the moment the export ran.
    Stamping them with the run time would change this file on every execution
    and produce an empty commit a day, drowning the real price movements in
    noise. A data package version should describe the data anyway.
    """
    latest_observation = max(
        detail["last_observation"] for detail in stats["markets"].values()
    )
    schema = json.loads((REPO / "schema.json").read_text(encoding="utf-8"))
    resources = [
        {
            "name": "latest",
            "path": "latest.csv",
            "title": "Most recent observation of each model, per market",
            "profile": "tabular-data-resource",
            "format": "csv",
            "mediatype": "text/csv",
            "encoding": "utf-8",
            "schema": schema,
        }
    ]
    for market, month in files:
        resources.append(
            {
                "name": f"{market.lower()}-{month}",
                "path": f"data/{market.lower()}/{month}.csv",
                "title": f"{market} observations, {month}",
                "profile": "tabular-data-resource",
                "format": "csv",
                "mediatype": "text/csv",
                "encoding": "utf-8",
                "schema": schema,
            }
        )

    package = {
        "$schema": "https://specs.frictionlessdata.io/schemas/data-package.json",
        "profile": "tabular-data-package",
        "name": "refurbished-iphone-prices",
        "title": "Refurbished iPhone prices",
        "description": (
            "Entry prices of refurbished iPhone models, observed twice a day on "
            "the French, American, German and Spanish Back Market storefronts "
            "and kept as a dated time series."
        ),
        "homepage": "https://www.priceradar.live",
        "version": latest_observation[:10],
        "created": latest_observation,
        "licenses": [
            {
                "name": "CC-BY-4.0",
                "title": "Creative Commons Attribution 4.0 International",
                "path": "https://creativecommons.org/licenses/by/4.0/",
            }
        ],
        "contributors": [
            {
                "title": "Price Radar",
                "path": "https://www.priceradar.live",
                "role": "author",
            }
        ],
        "keywords": [
            "refurbished",
            "iphone",
            "smartphone",
            "price tracking",
            "time series",
            "e-commerce",
            "consumer electronics",
        ],
        "resources": resources,
    }
    (REPO / "datapackage.json").write_text(
        json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    base_url = env("SUPABASE_URL").rstrip("/")
    key = env("SUPABASE_ANON_KEY")

    raw = fetch_all(base_url, key)
    rows = [clean for clean in (normalise(row) for row in raw) if clean]
    skipped = len(raw) - len(rows)
    if not rows:
        sys.exit("No observation returned; refusing to overwrite the dataset.")

    # Monthly files, one folder per market.
    by_file: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        by_file[(row["market"], row["observed_at"][:7])].append(row)

    if DATA.exists():
        for stale in DATA.rglob("*.csv"):
            stale.unlink()

    for (market, month), bucket in sorted(by_file.items()):
        bucket.sort(key=lambda item: (item["observed_at"], item["model"]))
        write_csv(DATA / market.lower() / f"{month}.csv", bucket)

    # `latest.csv`: the most recent observation of each model, per market. This
    # is the file most people open first, so it lives at the root.
    latest: dict[tuple[str, str], dict] = {}
    for row in rows:
        latest[(row["market"], row["model"])] = row
    write_csv(
        REPO / "latest.csv",
        sorted(latest.values(), key=lambda item: (item["market"], item["model"])),
    )

    stats = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "observations": len(rows),
        "markets": {},
    }
    for market in MARKETS:
        subset = [row for row in rows if row["market"] == market]
        if not subset:
            continue
        stats["markets"][market] = {
            "observations": len(subset),
            "models": len({row["model"] for row in subset}),
            "first_observation": min(row["observed_at"] for row in subset),
            "last_observation": max(row["observed_at"] for row in subset),
            "currency": subset[-1]["currency"],
        }
    (REPO / "stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    write_datapackage(sorted(by_file), stats)

    print(f"{len(rows)} observations written, {skipped} rows skipped")
    for market, detail in stats["markets"].items():
        print(
            f"  {market}: {detail['observations']:>5} observations, "
            f"{detail['models']} models, "
            f"{detail['first_observation'][:10]} → {detail['last_observation'][:10]}"
        )


if __name__ == "__main__":
    main()
