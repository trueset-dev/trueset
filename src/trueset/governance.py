"""Governance metadata: enforcement + evidence, not a catalog.

trueset does not become a governance *platform* (catalogs, lineage graphs, IAM
are out of scope and well served elsewhere). It owns the half those tools are
weak on: **enforcement** (policy-as-code that actually gates a pipeline) and
**evidence** (deterministic, auditable proof that a policy held).

Governance arrives as OPTIONAL metadata on a check -- owner, sensitivity,
regulation, tags, description. A check with none of these behaves exactly as it
does today. The one load-bearing mechanism is `split_meta`: governance keys must
be separated from check kwargs in `build_check`, or the extra keys crash the
check constructor.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: keys that are governance metadata, not check-construction arguments
GOV_KEYS = {"owner", "sensitivity", "regulation", "tags", "description"}

#: classification levels, ordered least -> most sensitive
SENSITIVITY_ORDER: list[str] = ["public", "internal", "confidential", "pii", "pci", "phi"]

#: the levels that count as "sensitive" for policy reports
SENSITIVE_LEVELS: frozenset[str] = frozenset({"pii", "pci", "phi", "confidential"})


@dataclass
class GovernanceMeta:
    """Optional, additive metadata describing a check's governance context."""

    owner: str | None = None
    sensitivity: str | None = None
    regulation: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str | None = None

    def __post_init__(self) -> None:
        # YAML lets `regulation:`/`tags:` be a bare string; normalize to a list.
        if isinstance(self.regulation, str):
            self.regulation = [self.regulation]
        if isinstance(self.tags, str):
            self.tags = [self.tags]
        if self.sensitivity is not None:
            level = str(self.sensitivity).lower()
            if level not in SENSITIVITY_ORDER:
                allowed = ", ".join(SENSITIVITY_ORDER)
                raise ValueError(
                    f"invalid sensitivity '{self.sensitivity}'. allowed: {allowed}"
                )
            self.sensitivity = level

    def is_set(self) -> bool:
        return any([self.owner, self.sensitivity, self.regulation, self.tags, self.description])

    @property
    def is_sensitive(self) -> bool:
        return self.sensitivity in SENSITIVE_LEVELS

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner,
            "sensitivity": self.sensitivity,
            "regulation": list(self.regulation),
            "tags": list(self.tags),
            "description": self.description,
        }


def split_meta(spec: dict[str, Any]) -> tuple[dict[str, Any], GovernanceMeta]:
    """Split a check spec into (check kwargs, governance metadata).

    THE load-bearing mechanism. Governance keys are pulled out before the check
    is constructed so they never reach the check's ``__init__``.
    """
    gov = {k: v for k, v in spec.items() if k in GOV_KEYS}
    rest = {k: v for k, v in spec.items() if k not in GOV_KEYS}
    return rest, GovernanceMeta(**gov)


BY_DIMENSIONS = ("sensitivity", "owner", "regulation")
NONE_GROUP = "(none)"


def group_results(results, by: str) -> list[dict[str, Any]]:
    """Group check results by a governance dimension for policy reporting.

    Returns an ordered list of ``{"group", "counts", "passed", "results"}``.
    A result with no value for the dimension lands in the ``(none)`` group;
    for ``regulation`` (a list) a result can appear under several groups.
    Works on any object exposing ``.status`` and ``.meta`` -- no result import,
    so this module stays a leaf dependency.
    """
    if by not in BY_DIMENSIONS:
        raise ValueError(f"cannot group by '{by}'. choose one of: {', '.join(BY_DIMENSIONS)}")

    buckets: dict[str, list] = {}
    for r in results:
        if by == "regulation":
            keys = [str(x) for x in r.meta.regulation] or [NONE_GROUP]
        else:
            val = getattr(r.meta, by)
            keys = [str(val)] if val else [NONE_GROUP]
        for k in keys:
            buckets.setdefault(k, []).append(r)

    out = []
    for name, rs in buckets.items():
        counts = {"pass": 0, "fail": 0, "error": 0}
        for r in rs:
            counts[r.status.value] += 1
        out.append(
            {
                "group": name,
                "counts": counts,
                "passed": all(r.ok for r in rs),
                "results": rs,
            }
        )

    def sort_key(entry: dict[str, Any]):
        name = entry["group"]
        none_last = 1 if name == NONE_GROUP else 0
        if by == "sensitivity" and name in SENSITIVITY_ORDER:
            # most sensitive first
            return (none_last, -SENSITIVITY_ORDER.index(name), name)
        return (none_last, 0, name)

    out.sort(key=sort_key)
    return out
