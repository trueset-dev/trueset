# Governance spec

Status: design, verified mechanism. Target: incremental, non-breaking.

## Positioning (read this first)

trueset does NOT become a governance *platform*. Catalogs, discovery/search UIs,
column-level lineage graphs, and access control / IAM are out of scope -- that
is DataHub / OpenMetadata / Collibra territory, a different product and an
enormous, well-served scope.

trueset owns the half of governance those tools are weak on: **enforcement and
evidence.** Catalogs *document* what should be true (passive). trueset *enforces*
policies and *proves* compliance happened (active, auditable). Governance here
is a metadata + reframing layer on top of the existing quality/reconciliation
core -- not a pivot.

In scope: policy-as-code, data classification, auditable evidence, data
contracts.
Out of scope: catalog, glossary, lineage graph, discovery UI, IAM. Compose with
those instead (see "Catalog composition").

## 1. Governance metadata on a check

Any check spec may carry optional governance fields. They are parsed OUT of the
spec before check-specific kwargs are constructed, then attached to the check
and copied onto every result.

```yaml
- type: not_null
  column: customer_ssn
  severity: error
  owner: risk-team            # accountable team/person
  sensitivity: pii            # public|internal|confidential|pii|pci|phi
  regulation: [gdpr, ccpa]    # free list of regime tags
  tags: [customer, identity]  # arbitrary labels
  description: "SSN must always be present for KYC"
```

`GovernanceMeta` (dataclass):

| field       | type        | notes                                             |
|-------------|-------------|---------------------------------------------------|
| owner       | str \| None | accountable party                                 |
| sensitivity | str \| None | one of the classification levels below            |
| regulation  | list[str]   | e.g. gdpr, ccpa, hipaa, sox, mifid2               |
| tags        | list[str]   | arbitrary                                         |
| description | str \| None | human-readable intent                             |

Classification levels (ordered): `public < internal < confidential < pii/pci/phi`.

## 2. Implementation (verified mechanism)

The load-bearing change is in `build_check`: split governance keys from check
kwargs, or extra kwargs crash the check constructor.

```python
# governance.py
from dataclasses import dataclass, field

@dataclass
class GovernanceMeta:
    owner: str | None = None
    sensitivity: str | None = None
    regulation: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    description: str | None = None
    def is_set(self) -> bool:
        return any([self.owner, self.sensitivity, self.regulation, self.tags])

GOV_KEYS = {"owner", "sensitivity", "regulation", "tags", "description"}

def split_meta(spec: dict):
    gov  = {k: v for k, v in spec.items() if k in GOV_KEYS}
    rest = {k: v for k, v in spec.items() if k not in GOV_KEYS}
    return rest, GovernanceMeta(**gov)
```

Threading:
- `Check` gains `self.meta: GovernanceMeta` (default empty).
- `build_check(spec)`: `rest, meta = split_meta(spec)`; build the check from
  `rest`; set `check.meta = meta`.
- `CheckResult` gains `meta: GovernanceMeta` (default empty); `Check._result`
  and every `evaluate` copy `self.meta` onto the result.
- `SuiteResult.to_dict()` serializes meta so evidence is machine-readable.

This is additive: checks with no governance fields behave exactly as today.

## 3. Reporting / policy queries

Once results carry meta, governance reporting is just filtering:

- "All failing policies on PII columns" -> results where
  `status == fail and meta.sensitivity in {pii, pci, phi}`.
- "Coverage by owner" -> group results by `meta.owner`.
- "GDPR posture" -> results where `"gdpr" in meta.regulation`.

Add `trueset report --checks ... --data ... --by sensitivity|owner|regulation` and
a JSON export. No new engine work -- it reads the results you already produce.

## 4. Classification (extends the profiler)

The profiler already infers semantic types (it detects email). Extend semantic
inference to suggest a `sensitivity` tag:

- Deterministic heuristics for the obvious, high-precision cases: email, phone,
  national-ID / SSN-like patterns, credit-card (Luhn), IBAN -> suggest `pii`/`pci`.
- The AI copilot (already built, already gated) handles fuzzy/semantic cases and
  drafts `owner`/`regulation` suggestions -- but output is reviewed and committed
  like any other check. AI classifies; humans and deterministic code decide.

`trueset suggest` gains classification output; suggested suites come pre-tagged for
review. Never auto-apply a sensitivity tag without human sign-off.

## 5. Data contracts

A contract is just a named, versioned check suite bound to a dataset boundary,
with an owner and an SLA. Nothing new structurally -- a suite file plus a small
header:

```yaml
contract: orders_v2
owner: data-platform
sla: { freshness_hours: 6 }
dataset: orders
checks: [ ... ]
```

Cross-system reconciliation is ALREADY contract enforcement between a producer
and a consumer system -- the hardest part exists. Contracts formalize the
naming, versioning, and ownership around it.

## 6. Auditable evidence

Every result is already deterministic JSON. Persisting run history (roadmap
Phase 4) turns that into an immutable audit trail: proof that dataset X met
policy Y on date Z. For regulated users (finance/health) that trail IS a
compliance deliverable. Requirement: results must stay deterministic and
non-AI-judged (already enforced).

## 7. Catalog composition (NOT catalog building)

Integrate with catalogs rather than replacing them:
- Push OUT: trueset's classifications and pass/fail evidence into DataHub /
  OpenMetadata (they hold the catalog + lineage).
- Pull IN: ownership and lineage from the catalog to enrich reports and route
  failures to the right owner.

This keeps trueset focused and makes it a good ecosystem citizen instead of a
challenger to entrenched catalogs.

## 8. How this maps onto the existing roadmap (not a detour)

| governance capability      | existing phase it rides on                    |
|----------------------------|-----------------------------------------------|
| metadata + policy queries  | small new increment (do first, ~1 PR)         |
| classification             | extends the profiler (Phase 2 work already)   |
| auditable evidence         | Phase 4 results-history                        |
| contracts                  | reconciliation (built) + a suite header       |
| catalog composition        | Phase 5 interop                               |

The immediate next build (Postgres backend) is unchanged. Governance is the halo
around the core, delivered mostly as metadata + reframing.

## First increment

Add `governance.py` (`GovernanceMeta`, `split_meta`), thread meta through
`Check`, `build_check`, `CheckResult`, and `SuiteResult.to_dict()`, and add
`trueset report --by {sensitivity|owner|regulation}`. Purely additive; all 25
existing tests must stay green. Add tests: a check with governance fields builds
correctly, meta appears on the result, and the report groups/filters correctly.
