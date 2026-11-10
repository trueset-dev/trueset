# Test drive — an end-to-end case study

Run trueset the way a real user would, start to finish, in ~15 minutes. The
story: **you're a data engineer on an e-commerce team. Orders flow from a
production Postgres database into a warehouse, and you need to trust them.**

Everything here uses the sample files in [`examples/`](https://github.com/trueset-dev/trueset/tree/main/examples),
so clone the repo (or download that folder) first:

```bash
git clone https://github.com/trueset-dev/trueset.git
cd trueset
pip install "trueset[sql]"
```

---

## 1. Your first check (a file)

Validate a CSV against a handful of rules:

```bash
trueset run --data examples/orders.csv --checks examples/checks.yml
```

You'll see a table — some checks pass, some fail — and the process exits
**non-zero** when an `error`-severity check fails. That exit code is what gates a
CI job, an Airflow task, or a pre-load step. Good data passes; bad data stops.

> Don't want to write checks by hand? `trueset suggest --data examples/orders.csv`
> drafts a starter suite from your data for you to review.

---

## 2. Cross-system reconciliation (the headline)

The thing single-table tools can't do: check that a dataset matches **another
system** — did the warehouse match the source after the load?

```bash
trueset reconcile \
  --data   examples/warehouse_orders.csv \
  --checks examples/reconcile.yml \
  --ref    source=examples/source_orders.csv
```

`value_parity` reports all three failure modes at once: values that differ on
shared keys, keys only in the warehouse, and keys only in the source. Row counts
can match while values silently drift — this is what catches it.

---

## 3. Run it against a real warehouse (Postgres)

The same checks run **in-place** on any SQL warehouse via SQLAlchemy — Snowflake,
BigQuery, Databricks, Redshift, Postgres — pushed down as SQL, so data never
moves. Let's prove it on Postgres. (Have Docker? Spin one up; otherwise point the
URL at any Postgres you have.)

```bash
# a throwaway Postgres on port 5433
docker run -d --name trueset-pg -e POSTGRES_PASSWORD=postgres -p 5433:5432 postgres:16

# load the sample orders into it
python - <<'PY'
import pandas as pd
from sqlalchemy import create_engine
e = create_engine("postgresql+psycopg://postgres:postgres@localhost:5433/postgres")
pd.read_csv("examples/orders.csv").to_sql("orders", e, index=False, if_exists="replace")
print("loaded orders into Postgres")
PY

# validate the live table — identical checks, now pushed down as SQL
trueset run \
  --url   "postgresql+psycopg://postgres:postgres@localhost:5433/postgres" \
  --table orders \
  --checks examples/checks.yml
```

Same suite, same verdict — in memory or in the warehouse. (Swap the URL for
`snowflake://…`, `bigquery://…`, `databricks://…`, etc. with the matching
SQLAlchemy driver installed.)

---

## 4. Already have dbt tests? Adopt them, don't rewrite them

Point trueset at a dbt `schema.yml` and it converts your existing tests into a
runnable trueset suite — `not_null`/`unique` map directly, `accepted_values` →
`in_set`, `relationships` → `referential_integrity`.

```bash
# a minimal dbt schema.yml
cat > schema.yml <<'YAML'
version: 2
models:
  - name: orders
    columns:
      - name: order_id
        tests:
          - not_null
          - unique
      - name: status
        tests:
          - accepted_values:
              values: [pending, shipped, delivered, cancelled]
YAML

# convert dbt tests -> a trueset suite
trueset import-dbt --schema schema.yml --model orders --out from_dbt.yml

# run the converted suite (anywhere — file, or the Postgres table from step 3)
trueset run --data examples/orders.csv --checks from_dbt.yml
```

Now the same checks run in CI, in your pipeline, and cross-warehouse — without
leaving dbt behind.

---

## 5. Quarantine the bad rows (shift-left)

trueset doesn't just flag bad data — it hands you the bad **rows** so your
pipeline can dead-letter them and keep the clean ones moving:

```bash
trueset run \
  --data examples/orders.csv \
  --checks examples/checks.yml \
  --quarantine bad_rows.csv \
  --save sqlite:///trueset_history.db
```

`bad_rows.csv` now holds the failing rows (with a `_trueset_reasons` column),
ready for a dead-letter sink — and the run, including how many rows were
rerouted, is saved to the history store.

---

## 6. See it all — the dashboard

Run a few suites with `--save` pointing at the same store, then open the
centralized **Data Trust** view:

```bash
trueset dashboard --open
```

One trust score, the shift-left data flow (rows checked vs. rerouted), health by
quality dimension, your datasets, and an incident feed — including **volume
anomalies** the engine catches that no rule would (data that passes every check
but whose row count quietly collapsed). See [Dashboard](guides/dashboard.md).

---

## Clean up

```bash
docker rm -f trueset-pg        # if you started the throwaway Postgres
rm -f from_dbt.yml bad_rows.csv trueset_history.db trueset-dashboard.html schema.yml
```

That's the full loop: validate → reconcile → warehouse → dbt → quarantine →
dashboard. Found a rough edge? [Open an issue](https://github.com/trueset-dev/trueset/issues)
— that feedback is exactly what shapes the roadmap.
