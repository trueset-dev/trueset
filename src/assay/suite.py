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


class Suite:
    def __init__(self, name: str, checks: list[Check], dataset: str | None = None):
        self.name = name
        self.checks = checks
        self.dataset = dataset

    @classmethod
    def from_dict(cls, spec: dict[str, Any]) -> Suite:
        name = spec.get("suite") or spec.get("name") or "unnamed_suite"
        dataset = spec.get("dataset")
        raw_checks = spec.get("checks", [])
        checks = [build_check(c) for c in raw_checks]
        return cls(name=name, checks=checks, dataset=dataset)

    @classmethod
    def from_yaml(cls, path: str | Path) -> Suite:
        text = Path(path).read_text()
        return cls.from_dict(yaml.safe_load(text))

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
