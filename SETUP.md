# Setting the repository up

Everything in this repository is already generated and valid. Two steps remain
before the daily update runs on its own.

## 1. Two repository secrets

The exporter reads the observation store over its public REST endpoint. It needs
two values, set under **Settings → Secrets and variables → Actions → New
repository secret**:

| Secret | Value |
| --- | --- |
| `SUPABASE_URL` | The project URL, e.g. `https://xxxxxxxx.supabase.co` |
| `SUPABASE_ANON_KEY` | The anon (public) key of the same project |

Both are the values the public website already ships in its own pages, so
neither is a credential in the usual sense — the anon key only grants the
read-only access the site itself uses. They live in secrets rather than in the
workflow file so that rotating them never means editing code.

> Use the **anon** key, never the service role key. The service role key
> bypasses row level security and has no business in a public repository.

## 2. Allow the workflow to push

Under **Settings → Actions → General → Workflow permissions**, select
**Read and write permissions**. The workflow itself only asks for
`contents: write`, but that repository-level setting has to allow it.

## 3. One placeholder to replace

`README.md` contains a `raw.githubusercontent.com/OWNER/priceradar-dataset/…`
URL in the quick-start example. Replace `OWNER` with the account or organisation
the repository lives under, so the snippet is copy-pasteable.

## Checking it works

Run it once by hand: **Actions → Update dataset → Run workflow**. A successful
run either commits new observations or prints *"No new observation — nothing to
commit"*, which is the normal outcome between two collections.

## The schedule

Three runs a day, in UTC:

| Time | Why |
| --- | --- |
| 08:20 | Shortly after the morning collection (~07:00) |
| 16:20 | Shortly after the afternoon collection (~15:00) |
| 00:30 | Catches a late collection so a day is never skipped |

A run that finds nothing new exits without committing, so the history stays a
record of price movements rather than a log of cron firings.

## Running the scripts locally

```bash
export SUPABASE_URL="https://xxxxxxxx.supabase.co"
export SUPABASE_ANON_KEY="…"

python3 scripts/export_dataset.py     # rewrites data/, latest.csv, stats.json, datapackage.json
python3 scripts/render_chart.py       # redraws assets/price-history-fr.svg from the CSVs
python3 scripts/validate_dataset.py   # checks every file against schema.json
```

No dependencies: the standard library is enough, and Python 3.10 or later will
do.

The export is deterministic — same data in, byte-identical files out — so you
can run it freely without creating spurious diffs.

## Adding a market

Nothing in the scripts is hardcoded to a country beyond the list of accepted
codes:

1. add the code to `MARKETS` in `scripts/export_dataset.py`;
2. add it to the `market` enum in `schema.json`, and its currency to the
   `currency` enum if it is a new one;
3. run the export — the monthly files, `datapackage.json` and `stats.json`
   follow on their own;
4. add a row to the coverage table in `README.md`.

## If a run fails

- **`Missing environment variable …`** — the secrets are not set, or are named
  differently. See step 1.
- **`HTTP 401` or `HTTP 403`** — wrong key, or the anon role lost its read grant
  on the table.
- **`No observation returned; refusing to overwrite the dataset.`** — the query
  came back empty. The exporter stops on purpose rather than committing an empty
  dataset over a good one.
- **A validation error** — the export produced something that no longer matches
  `schema.json`. Nothing is committed; fix the schema or the exporter, whichever
  is actually wrong.
