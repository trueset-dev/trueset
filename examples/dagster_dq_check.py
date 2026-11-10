"""Reference Dagster definitions: trueset as a first-class asset check.

Copy into your Dagster project. Requires `dagster` and `trueset` installed -- it
is a starting point, not run by trueset's tests.

Modelling data quality as an `asset_check` means the result (pass/fail + the
evidence) shows up right on the `orders` asset in the Dagster UI, and a failure
can block downstream assets.
"""

from __future__ import annotations

import pandas as pd
from dagster import AssetCheckResult, asset, asset_check

from trueset import validate_dataframe

CHECKS = "dq/checks.yml"


@asset
def orders() -> pd.DataFrame:
    return pd.read_csv("/data/orders.csv")


@asset_check(asset=orders)
def orders_quality(orders: pd.DataFrame) -> AssetCheckResult:
    result = validate_dataframe(orders, CHECKS)
    return AssetCheckResult(
        passed=result.passed,
        metadata=result.to_dict(),  # evidence surfaces in the Dagster UI
    )
