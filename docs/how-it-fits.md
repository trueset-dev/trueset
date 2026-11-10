# How trueset fits your stack

The one thing to understand about trueset: **it travels with your data.** The
same check runs in your pipeline *before* data lands, inside your warehouse
*after* it lands, and *across* two systems to prove they agree.

That's the difference from a warehouse-only tool like dbt, which can only test
data that is **already** in the warehouse.

```
  SOURCE              INGESTION / PIPELINE            WAREHOUSE
  (DB, API,    ──►    Python / CSV / stream    ──►    Snowflake · BigQuery ·
   files)             (Airflow, Spark, CI)            Postgres · Databricks · …
                             │                               │
                     ✅ trueset here                  ✅ trueset here
                     catch bad data                   push checks down as SQL,
                     BEFORE it lands                  data never leaves
                             │                               │
                             └──── ✅ trueset reconciles the two ────┘
                              did the warehouse match the source?
```

## In your pipeline (shift-left)

trueset is a `pip install`, so it runs as an ordinary step in your pipeline — in
Airflow, Spark, dbt's surrounding orchestration, or a CI job — on a DataFrame, a
file, or a stream. Because it runs *before* the load, it can stop bad data from
ever reaching the warehouse, and its exit code gates the step:

```bash
trueset run --data orders.csv --checks checks.yml   # non-zero exit on failure
```

```python
from trueset import validate_dataframe
result = validate_dataframe(df, "checks.yml")        # inside a pipeline task
if not result.passed:
    ...                                              # route / block / alert
```

## In your warehouse (in place, as SQL)

Point the *same* `checks.yml` at a live table and trueset pushes each check down
as SQL — so the full table never leaves the warehouse. Only the source changes
from `--data` to `--url` + `--table`:

```bash
trueset run --url "snowflake://…" --table orders --checks checks.yml
```

This is the layer dbt also operates in. trueset works with **any
SQLAlchemy-supported database** — Snowflake, BigQuery, Postgres, Databricks,
Redshift, MySQL, SQL Server, Oracle, ClickHouse, … — the command is identical;
only the URL and the installed driver change.

## Across systems (reconciliation)

The part most tools can't do: check that one system **matches** another — did the
warehouse actually equal the source after the load? Row counts can match while
values silently drift; `value_parity` catches it.

```bash
trueset reconcile --data warehouse_orders.csv --checks reconcile.yml \
  --ref source=source_orders.csv
```

## trueset vs. dbt, at a glance

| | In your pipeline (pre-load) | In your warehouse (post-load) | Across two systems |
|---|:---:|:---:|:---:|
| **dbt tests** | ❌ needs data already loaded | ✅ | ❌ |
| **trueset** | ✅ | ✅ | ✅ |

They're complementary: keep your dbt tests (trueset can even
[import them](getting-started.md)), and use trueset to extend the same quality
bar earlier in the pipeline and across systems.

> In one line: **dbt tests live where your data already is; trueset travels with
> your data — before the load, after the load, and between systems.**
