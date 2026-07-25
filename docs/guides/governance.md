# Governance & classification

trueset is not a catalog or a lineage graph (that's DataHub / OpenMetadata /
Collibra territory — compose with them, don't rebuild them). It owns the half
those tools are weak on: **enforcement and evidence.** Governance here is optional
metadata on checks, not a new subsystem.

## Metadata on a check

Any check may carry optional governance fields — they're additive and change
nothing about how the check runs:

```yaml
- type: not_null
  column: customer_ssn
  severity: error
  owner: risk-team                 # accountable party
  sensitivity: pii                 # public|internal|confidential|pii|pci|phi
  regulation: [gdpr, ccpa]         # free list of regime tags
  tags: [customer, identity]
  description: "SSN required for KYC"
```

The metadata rides onto every `CheckResult` and serializes into the JSON evidence,
so a persisted run becomes an auditable record: *dataset X met policy Y on date Z*.

## Policy reports

Once results carry metadata, governance reporting is just grouping:

```bash
trueset report --data orders.csv --checks governed_checks.yml --by sensitivity
trueset report --data orders.csv --checks governed_checks.yml --by owner
trueset report --data orders.csv --checks governed_checks.yml --by regulation
```

This surfaces, e.g., *all failing checks on PII columns owned by the risk team* —
directly from the results you already produce.

## Data classification

`trueset profile` infers a suggested `sensitivity` for high-precision patterns —
email, phone, US SSN, credit card (Luhn, even as a bare integer), IBAN → `pii` /
`pci`:

```bash
trueset profile --data customers.csv     # shows an inferred sensitivity column
```

`trueset suggest` then pre-tags the drafted checks with the suggested sensitivity.

!!! note "Suggested, never imposed"
    Both the deterministic profiler and the AI copilot only *suggest* tags. trueset
    never auto-applies a classification — a human reviews and commits it, the same
    trust rule as checks.
