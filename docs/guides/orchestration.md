# Orchestration — run trueset in your pipeline

trueset is a `pip install` and a CLI with a meaningful **exit code**, so it drops
into any orchestrator as an ordinary step. There's nothing trueset-specific to
learn on the orchestrator side: run a check, and let a non-zero exit (any
`error`-severity failure) fail the task and stop bad data moving downstream.

Two patterns cover almost everything:

- **Gate** — run a check as its own task; if it fails, the pipeline stops.
- **Quarantine-and-continue** — `split` the batch, load the clean rows, send the
  bad ones to a dead-letter sink, keep going.

Runnable references live in the repo:
[`examples/airflow_dq_dag.py`](https://github.com/trueset-dev/trueset/blob/main/examples/airflow_dq_dag.py)
and [`examples/dagster_dq_check.py`](https://github.com/trueset-dev/trueset/blob/main/examples/dagster_dq_check.py).

## Airflow

### Simplest — a gate with `BashOperator`

```python
from airflow.operators.bash import BashOperator

check = BashOperator(
    task_id="dq_gate",
    # non-zero exit on any error-severity failure fails the task
    bash_command="trueset run --data /data/orders.csv --checks /dq/checks.yml "
                 "--save postgresql+psycopg://warehouse/dq",
)
extract >> check >> load          # load only runs if the gate passes
```

### In-memory — `PythonOperator` with the API

```python
from airflow.exceptions import AirflowFailException
from trueset import validate_dataframe

def dq_gate(**ctx):
    df = ctx["ti"].xcom_pull(task_ids="extract")      # a DataFrame
    result = validate_dataframe(df, "/dq/checks.yml")
    if not result.passed:
        raise AirflowFailException(f"data quality failed: {result.to_dict()}")
```

### Quarantine-and-continue

```python
from trueset import Suite, split

def load_clean(**ctx):
    df = ctx["ti"].xcom_pull(task_ids="extract")
    sp = split(df, Suite.from_yaml("/dq/checks.yml"))
    sp.bad_annotated().to_csv("/dead_letter/bad.csv", index=False)   # reasons attached
    sp.good.to_sql("orders", warehouse_engine, if_exists="append")  # clean rows flow
```

## Dagster

Model data quality as a first-class **asset check** so it shows up on the asset:

```python
from dagster import asset_check, AssetCheckResult
from trueset import validate_dataframe

@asset_check(asset="orders")
def orders_quality(orders):                 # `orders` is the upstream asset's value
    result = validate_dataframe(orders, "checks.yml")
    return AssetCheckResult(
        passed=result.passed,
        metadata=result.to_dict(),          # evidence surfaces in the Dagster UI
    )
```

A failing check blocks downstream assets (or warns), per the check's severity.

## Prefect

```python
from prefect import task
from trueset import validate_dataframe

@task
def dq_gate(df):
    result = validate_dataframe(df, "checks.yml")
    if not result.passed:
        raise ValueError(f"data quality failed: {result.to_dict()}")
    return df
```

## CI (GitHub Actions)

trueset ships a composite Action, so a pull request can be gated on data quality:

```yaml
- uses: trueset-dev/trueset@main
  with:
    data: data/orders.csv
    checks: dq/checks.yml
```

Or without the Action — just the CLI, which works in any CI system:

```yaml
- run: pip install "trueset[sql]"
- run: trueset run --data data/orders.csv --checks dq/checks.yml
```

## In the warehouse

Every recipe above works against a live warehouse table too — swap `--data` for
`--url` + `--table` (CLI), so the checks run as SQL where the data already lives:

```bash
trueset run --url "$WAREHOUSE_URL" --table orders --checks dq/checks.yml
```

See [How it fits your stack](../how-it-fits.md) for pipeline-vs-warehouse, and
[Pipelines & quarantine](pipelines.md) for the routing details.
