# Working on the dataset locally

The dataset updates itself from a container running on our own server — see
[DEPLOY-COOLIFY.md](DEPLOY-COOLIFY.md) for that. This page covers running the
scripts by hand, on your machine.

## The two values you need

| Variable | Value |
| --- | --- |
| `SUPABASE_URL` | The project URL, e.g. `https://xxxxxxxx.supabase.co` |
| `SUPABASE_ANON_KEY` | The anon (public) key of the same project |

Both are the values the public website already ships in its own pages, so
neither is a credential in the usual sense — the anon key only grants the
read-only access the site itself uses.

> Use the **anon** key, never the service role key. The service role key
> bypasses row level security and has no business in a public repository.

Copy `.env.example` to `.env` and fill them in.

## Without Docker

```bash
SUPABASE_URL=… SUPABASE_ANON_KEY=… bash scripts/update.sh
```

Nothing to install: the scripts use the standard library only, and any Python
3.10 or later will do.

## In Docker

The `local` profile mounts your working copy instead of the container's own
clone, so you work on the files in front of you:

```bash
docker compose --profile local run --rm local
docker compose --profile local run --rm local python3 scripts/validate_dataset.py
```

The image holds only the entrypoint: scripts, schema and data all come from the
repository, so the container always runs the version that ships with the data
it is updating.

`PUSH` defaults to off — running a container must never publish to a public
repository by surprise.

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
