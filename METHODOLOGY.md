# Methodology

How the figures in this repository are produced, what they describe, and what
they deliberately do not.

## What is recorded

For a fixed catalogue of refurbished iPhone models, on each of the four
storefronts covered, the collector reads the **publicly displayed entry
price** — the cheapest offer visible for that model at that moment.

Each reading is stored with its timestamp and never overwritten. A price is a
dated observation, not a state that gets updated: that is what makes the series
a series.

The `reference_new_price` column holds the new price displayed by the source for
the same model, when it shows one. It exists only for models still sold new, and
it is read, never estimated.

## Why the entry price

Storage and cosmetic grade change what a buyer actually pays. Tracking every
combination would mean tracking dozens of variants per model, most of which
appear and disappear with stock.

A single, consistently defined figure — *the cheapest offer visible for this
model right now* — stays comparable across models and across months. It is less
precise than a per-variant price, and more honest than an average across
variants that no one ever paid.

The consequence is stated plainly in the README: this dataset cannot tell you
what a specific configuration costs.

## Collection frequency

Once or twice a day per market, at a low request rate.

The rhythm is a deliberate choice, not a technical limit. A price tracker has no
need to hammer a marketplace, and a fixed catalogue read twice a day is enough
to see every meaningful move while staying a negligible load on the source.

## What can make a price move

Understanding this matters more than the raw number.

The displayed price is the **cheapest offer among many sellers**, not a list
price set by the marketplace. It therefore moves for reasons that have nothing
to do with anyone changing a price:

- the seller holding the cheapest offer runs out of stock, and the visible price
  jumps to the next cheapest;
- a batch of trade-ins reaches a refurbisher and pushes the entry price down;
- the cheapest offer was a heavily marked unit, it sells, and the visible price
  rises although nothing got more expensive;
- a new Apple generation ships and trade-ins flow in over the following weeks.

A single point is close to meaningless. A series is what carries information.

## Collection ethics

The collector is built as a cautious observer, not a crawler. In practice:

- a manually maintained allowlist of pages — no recursive link discovery, no
  broad crawling;
- `robots.txt` checked before a source is activated;
- the worker identifies itself in its user agent;
- no CAPTCHA, challenge or block is ever circumvented;
- no authentication, no account creation, no access to non-public areas;
- no simulation of a purchase path, and no action that could change a cart,
  a price, a stock level or a session;
- automatic stop on repeated abnormal responses, with a per-country kill switch;
- no personal data, no account data, no payment data, no proprietary tracking
  data is collected at any point.

## Validation

Before an observation is stored it must pass content checks: the price has to
parse as a number, fall inside a plausible range for that market, and belong to
a model on the allowlist. A reading that fails is rejected rather than stored
and corrected later.

Rejections are visible in the series as a gap: a model can therefore have fewer
observations than its neighbours on a given day. Nothing is interpolated to fill
such a gap.

## What is not published here

The dataset publishes the series that collection produced — an observation over
time that did not exist before it was recorded.

It leaves out material that belongs to the source rather than to the
observation: product URLs, seller identity, images, ratings and review counts.
The goal is a dataset that supports price research without standing in for the
marketplace's own catalogue.

## Reproducibility

`scripts/export_dataset.py` regenerates every CSV from the observation store.
Its output is deterministic — sorted rows, fixed decimal formatting, fixed line
endings — so running it on unchanged data produces byte-identical files. That is
what makes the commit history meaningful: a commit exists only when a new
observation landed.

`scripts/render_chart.py` regenerates the README chart from the published CSVs,
not from the database, so the picture always matches the files in the
repository.

## Known limits

- Two readings a day: anything that moves and reverts in between is invisible.
- Entry price only: not a per-variant price.
- No currency conversion, ever: markets are separate series.
- Short history: collection began 13 August 2026 for France, later elsewhere.
  Long-horizon claims are not supported by this data, and should not be made
  from it.
