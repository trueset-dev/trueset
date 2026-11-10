# Dashboard — the centralized Data Trust view

`trueset dashboard` turns your run history into one self-contained HTML page: a
single **Data Trust Score**, the shift-left **data flow** (rows checked vs.
rerouted to quarantine), health by **quality dimension** (freshness,
completeness, validity, uniqueness, volume, reconciliation), a dense asset table,
and an **incident feed** — including anomalies the engine catches that no
single-table check would (a dataset that passes every rule but whose volume
quietly collapsed).

It reads data trueset already produces — no server, no cloud, no extra
dependencies. It's the open-source seed of the hosted hub.

## Use it

Save your runs to a history store, then open the dashboard:

```bash
# 1. save each run to a store (SQLite locally, or Postgres/Snowflake for a team)
trueset run --data orders.csv --checks checks.yml --save sqlite:///trueset_history.db

# 2. open the centralized view
trueset dashboard --open
```

Options:

| Flag | Default | What it does |
|------|---------|--------------|
| `--store` | `sqlite:///trueset_history.db` | Results store to read (any SQLAlchemy URL). |
| `--out` | `trueset-dashboard.html` | Where to write the HTML. |
| `--open` | off | Open it in your browser when done. |
| `--limit` | 400 | Max recent runs to read. |

## What it shows

- **Data Trust Score** + a trust-over-time chart, with the change over the window.
- **Data flow** — rows checked vs. rerouted to a dead-letter sink. Populate the
  rerouted number by running with `--quarantine` (see
  [Pipelines & quarantine](pipelines.md)).
- **Quality by dimension** — each check type maps to a dimension; freshness is
  framed as an SLA.
- **Volume-anomaly detection** — surfaces the engine's anomaly detection over run
  history (a silent failure: data that passes every check but whose row volume
  deviates from its baseline).
- **Monitored datasets** — status, trust, freshness, rows, rerouted, checks, trend.
- **Open incidents** — failing checks, freshness breaches, and volume anomalies,
  most-severe first.

## Populate it realistically

The dashboard gets richer as history accumulates. Run your suites on a schedule
(cron, Airflow, a CI job) with `--save` pointing at the same store, and
`--quarantine` where you dead-letter bad rows, so the flow and trend panels fill
in. For a team, point `--store` at a shared Postgres instead of a local SQLite
file and everyone reads the same view.
