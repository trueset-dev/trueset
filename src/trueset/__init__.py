"""trueset -- write a data-quality check once, run it anywhere.

The public API is intentionally small.
"""

from __future__ import annotations

from .backends.pandas_backend import PandasBackend
from .checks import Check, available_checks, build_check
from .result import CheckResult, Severity, Status, SuiteResult
from .suite import Suite, SuiteLoadError

try:  # optional -- only if the [sql] extra is installed
    from .backends.duckdb_backend import DuckDBBackend
except Exception:  # pragma: no cover
    DuckDBBackend = None  # type: ignore
from .profile import DatasetProfile, profile_dataframe, suggest_from_profile
from .reconcile import (
    ReconciliationCheck,
    ReferentialIntegrity,
    RowCountParity,
    ValueParity,
)

__version__ = "0.0.1"

__all__ = [
    "Suite",
    "SuiteLoadError",
    "Check",
    "CheckResult",
    "SuiteResult",
    "Severity",
    "Status",
    "PandasBackend",
    "DuckDBBackend",
    "build_check",
    "available_checks",
    "validate_dataframe",
    "profile_dataframe",
    "suggest_from_profile",
    "DatasetProfile",
    "ReconciliationCheck",
    "RowCountParity",
    "ReferentialIntegrity",
    "ValueParity",
]


def validate_dataframe(df, suite):
    """Convenience: run a Suite (or YAML path) against a pandas DataFrame."""
    from pathlib import Path

    if isinstance(suite, (str, Path)):
        suite = Suite.from_yaml(suite)
    return suite.run(PandasBackend(df))
