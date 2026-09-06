#!/usr/bin/env python3
"""Draw the chart shown in the README, from the CSV files of this repository.

It reads the published data rather than the database on purpose: the picture in
the README is then guaranteed to show exactly what the repository contains, and
anyone can regenerate it without credentials.

The SVG paints its own light background instead of inheriting the page's. GitHub
renders README images on a dark canvas in dark mode, and a transparent chart
with dark axes would become unreadable there.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = REPO / "assets" / "price-history-fr.svg"

MARKET = "FR"
# Four generations, from the cheapest tracked model to the current flagship:
# enough to show that the series separate, few enough to stay readable.
MODELS = ["iPhone 13", "iPhone 14", "iPhone 15", "iPhone 16"]
COLOURS = ["#1f7a5a", "#c2703d", "#4a6fa5", "#8a4f7d"]

WIDTH, HEIGHT = 960, 420
LEFT, RIGHT, TOP, BOTTOM = 64, 210, 44, 56
INK = "#102019"
MUTED = "#66736b"
GRID = "#dcd6c8"
PAPER = "#fffaf0"


def read_series() -> dict[str, list[tuple[date, float]]]:
    daily: dict[str, dict[date, float]] = defaultdict(dict)
    for path in sorted((REPO / "data" / MARKET.lower()).glob("*.csv")):
        with path.open(encoding="utf-8", newline="") as handle:
            for row in csv.DictReader(handle):
                if row["model"] not in MODELS:
                    continue
                day = datetime.strptime(row["observed_at"], "%Y-%m-%dT%H:%M:%SZ").date()
                # One point per day: the lowest entry price observed that day,
                # which is the figure a buyer could actually have acted on.
                price = float(row["price"])
                current = daily[row["model"]].get(day)
                daily[row["model"]][day] = price if current is None else min(current, price)
    return {model: sorted(points.items()) for model, points in daily.items()}


def escape(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def main() -> None:
    series = read_series()
    if not series:
        raise SystemExit("No data found; run scripts/export_dataset.py first.")

    days = sorted({day for points in series.values() for day, _ in points})
    prices = [price for points in series.values() for _, price in points]
    first, last = days[0], days[-1]
    span = max((last - first).days, 1)

    low, high = min(prices), max(prices)
    pad = (high - low) * 0.12 or 10
    low, high = low - pad, high + pad

    def x(day: date) -> float:
        return LEFT + (day - first).days / span * (WIDTH - LEFT - RIGHT)

    def y(price: float) -> float:
        return TOP + (high - price) / (high - low) * (HEIGHT - TOP - BOTTOM)

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" '
        f'width="{WIDTH}" height="{HEIGHT}" role="img" '
        f'aria-label="Entry price of four refurbished iPhone models on the French market">',
        f'<rect width="{WIDTH}" height="{HEIGHT}" fill="{PAPER}"/>',
        f'<style>text{{font-family:ui-sans-serif,system-ui,-apple-system,'
        f'"Segoe UI",Roboto,sans-serif}}</style>',
        f'<text x="{LEFT}" y="26" font-size="15" font-weight="700" fill="{INK}">'
        f"Refurbished iPhone entry price · Back Market France</text>",
    ]

    # Horizontal grid and price labels.
    steps = 4
    for index in range(steps + 1):
        price = low + (high - low) * index / steps
        py = y(price)
        parts.append(
            f'<line x1="{LEFT}" y1="{py:.1f}" x2="{WIDTH - RIGHT}" y2="{py:.1f}" '
            f'stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{LEFT - 10}" y="{py + 4:.1f}" font-size="11" '
            f'fill="{MUTED}" text-anchor="end">{price:.0f} €</text>'
        )

    # Date labels: first, middle and last observed day.
    for day in (first, first + (last - first) / 2, last):
        parts.append(
            f'<text x="{x(day):.1f}" y="{HEIGHT - BOTTOM + 20:.1f}" font-size="11" '
            f'fill="{MUTED}" text-anchor="middle">{day.strftime("%d %b %Y")}</text>'
        )

    # One line per model, plus a dot on the last point.
    for index, model in enumerate(MODELS):
        points = series.get(model)
        if not points:
            continue
        colour = COLOURS[index % len(COLOURS)]
        path = " ".join(
            f"{'M' if position == 0 else 'L'}{x(day):.1f},{y(price):.1f}"
            for position, (day, price) in enumerate(points)
        )
        parts.append(
            f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="2.5" '
            f'stroke-linejoin="round" stroke-linecap="round"/>'
        )
        end_day, end_price = points[-1]
        parts.append(
            f'<circle cx="{x(end_day):.1f}" cy="{y(end_price):.1f}" r="4" fill="{colour}"/>'
        )
        legend_y = TOP + 16 + index * 24
        parts.append(
            f'<rect x="{WIDTH - RIGHT + 24}" y="{legend_y - 9:.0f}" width="18" height="4" '
            f'rx="2" fill="{colour}"/>'
        )
        parts.append(
            f'<text x="{WIDTH - RIGHT + 50}" y="{legend_y - 1:.0f}" font-size="12" '
            f'fill="{INK}">{escape(model)}</text>'
        )
        parts.append(
            f'<text x="{WIDTH - RIGHT + 50}" y="{legend_y + 13:.0f}" font-size="11" '
            f'fill="{MUTED}">{end_price:.0f} €</text>'
        )

    parts.append(
        f'<text x="{LEFT}" y="{HEIGHT - 14}" font-size="10.5" fill="{MUTED}">'
        f"Lowest entry price observed each day · generated from the CSV files in this repository"
        f"</text>"
    )
    parts.append("</svg>")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(REPO)} written — {len(days)} days, {len(series)} models")


if __name__ == "__main__":
    main()
