"""Structured results for checks and suites.

These are plain dataclasses so they serialize cleanly to JSON (for CI,
dashboards, or shipping to a warehouse) and stay decoupled from any
particular execution engine.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """How much a failing check matters.

    WARN surfaces the problem but does not fail the run (exit 0).
    ERROR fails the run (non-zero exit), so it can gate a CI pipeline.
    """

    WARN = "warn"
    ERROR = "error"


class Status(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"  # the check itself blew up (bad config, missing column, ...)


@dataclass
class CheckResult:
    check: str
    status: Status
    severity: Severity
    column: str | None = None
    observed: Any = None
    total_rows: int | None = None
    failing_rows: int | None = None
    message: str = ""

    @property
    def ok(self) -> bool:
        """True if this result should NOT fail the run."""
        return self.status is Status.PASS or self.severity is Severity.WARN

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        d["severity"] = self.severity.value
        return d


@dataclass
class SuiteResult:
    name: str
    dataset: str | None = None
    results: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """A suite passes if nothing with ERROR severity failed."""
        return all(r.ok for r in self.results)

    @property
    def counts(self) -> dict[str, int]:
        c = {"pass": 0, "fail": 0, "error": 0, "warn": 0}
        for r in self.results:
            c[r.status.value] += 1
            if r.status is not Status.PASS and r.severity is Severity.WARN:
                c["warn"] += 1
        return c

    def to_dict(self) -> dict[str, Any]:
        return {
            "suite": self.name,
            "dataset": self.dataset,
            "passed": self.passed,
            "counts": self.counts,
            "results": [r.to_dict() for r in self.results],
        }
