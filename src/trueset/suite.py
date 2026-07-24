"""A Suite is a named collection of checks plus a runner.

Suites can be built in Python or loaded from YAML. Running a suite against
any Backend yields a SuiteResult.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .backends.base import Backend
from .checks import Check, build_check
from .reconcile import ReconciliationCheck  # noqa: F401  (import also registers recon checks)
from .result import CheckResult, Status, SuiteResult


class SuiteLoadError(ValueError):
    """Raised when a suite cannot be built from a dict/YAML (bad structure,
    unknown check type, or invalid check arguments). Carries a human-readable
    message the CLI can show without a traceback."""


class Suite:
    def __init__(self, name: str, checks: list[Check], dataset: str | None = None):
        self.name = name
        self.checks = checks
        self.dataset = dataset

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> Suite:
        if not isinstance(spec, dict):
            raise SuiteLoadError(
                f"suite must be a mapping with a 'checks:' list, got {type(spec).__name__}"
            )
        name = spec.get("suite") or spec.get("name") or "unnamed_suite"
        dataset = spec.get("dataset")
        raw_checks = spec.get("checks", [])
        if not isinstance(raw_checks, list):
            raise SuiteLoadError("'checks' must be a list")
        checks: list[Check] = []
        for i, c in enumerate(raw_checks):
            if not isinstance(c, dict):
                raise SuiteLoadError(f"check #{i + 1} must be a mapping, got {c!r}")
            try:
                checks.append(build_check(c))
            except (ValueError, TypeError) as exc:
                raise SuiteLoadError(f"check #{i + 1} ({c.get('type', '?')}): {exc}") from exc
        return cls(name=name, checks=checks, dataset=dataset)

    @classmethod
    def from_yaml(cls, path: str | Path) -> Suite:
        p = Path(path)
        if not p.exists():
            raise SuiteLoadError(f"checks file not found: {p}")
        try:
            spec = yaml.safe_load(p.read_text())
        except yaml.YAMLError as exc:
            raise SuiteLoadError(f"could not parse YAML in {p}: {exc}") from exc
        if spec is None:
            raise SuiteLoadError(f"checks file is empty: {p}")
        return cls.from_dict(spec)

    def run(
        self,
        backend: Backend,
        references: dict[str, Backend] | None = None,
    ) -> SuiteResult:
        references = references or {}
        results: list[CheckResult] = []
        for check in self.checks:
            try:
                if isinstance(check, ReconciliationCheck):
                    ref = references.get(check.reference)
                    if ref is None:
                        results.append(
                            CheckResult(
                                check=check.type,
                                status=Status.ERROR,
                                severity=check.severity,
                                message=f"reference '{check.reference}' not provided",
                            )
                        )
                        continue
                    results.append(check.evaluate(backend, ref))
                else:
                    results.append(check.evaluate(backend))
            except Exception as exc:  # a broken check should not kill the run
                results.append(
                    CheckResult(
                        check=getattr(check, "type", "check"),
                        status=Status.ERROR,
                        severity=check.severity,
                        message=f"check raised: {exc}",
                    )
                )
        return SuiteResult(name=self.name, dataset=self.dataset, results=results)
