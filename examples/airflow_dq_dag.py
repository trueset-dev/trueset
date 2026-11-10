"""Reference Airflow DAG: trueset as a data-quality gate + quarantine step.

Copy into your `dags/` folder. Requires `apache-airflow` and `trueset` installed
in the Airflow environment -- it is a starting point, not run by trueset's tests.

Pattern:
  extract -> dq_gate (stop on error-severity failure) -> load_clean (route bad rows)
"""

from __future__ import annotations

import pendulum
from airflow.decorators import dag, task
from airflow.exceptions import AirflowFailException

from trueset import Suite, split, validate_dataframe

CHECKS = "/opt/airflow/dq/checks.yml"


@dag(schedule="@daily", start_date=pendulum.datetime(2026, 1, 1), catchup=False)
def orders_quality():
    @task
    def extract():
        import pandas as pd

        return pd.read_csv("/data/orders.csv")

    @task
    def dq_gate(df):
        # A hard gate: any error-severity failure stops the pipeline here.
        result = validate_dataframe(df, CHECKS)
        if not result.passed:
            raise AirflowFailException(f"data quality failed: {result.to_dict()}")
        return df

    @task
    def load_clean(df):
        # Or quarantine-and-continue: load clean rows, dead-letter the rest.
        sp = split(df, Suite.from_yaml(CHECKS))
        sp.bad_annotated().to_csv("/dead_letter/orders_bad.csv", index=False)
        return {"loaded": len(sp.good), "quarantined": sp.n_bad}

    load_clean(dq_gate(extract()))


orders_quality()
