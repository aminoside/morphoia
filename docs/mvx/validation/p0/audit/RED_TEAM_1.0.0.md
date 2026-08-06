# P0 semantic red-team — protocol 1.0.0-p0

The original SHA-256 seal with root
`87f74f8196c3f9b3c7f512a8a4a1b04d17743428ef91982e4b6f2da29087cf9f`
was mechanically valid. Its G0 PASS was withdrawn before cohort selection or any
MVX experimental outcome because the semantic checks were incomplete.

## Blocking findings

1. Endpoint lists and the metric dictionary were not closed by exact equality.
2. Cohort, OOD and nested-milestone selection were not executable.
3. The production split salt was public and the holdout custodian was not yet
   required at G1.
4. The split implementation, CLI output and frozen vector did not implement all
   declared fields and leakage constraints.
5. P2 topology fields were required by a split that G1 attempted to create
   before P2.
6. A single Clopper–Pearson bound incorrectly treated six quota-sampled datasets
   and creator-correlated lineages as one IID population.
7. Usability classes, release denominators, systematic disadvantage and final
   decision precedence were not deterministic.
8. Schemas admitted contradictory PASS records and did not require output
   artifact hashes.
9. Payload states and job terminal statuses were conflated.
10. The seal command was not append-only.

## Disposition

- Effective verdict of 1.0.0-p0: **FAIL / SUPERSEDED**.
- Experimental outcomes observed: **none**.
- Production cohort or split created: **none**.
- Replacement protocol: **1.0.1-p0**.

The original seal, verdict and their hashes are retained unchanged in
`superseded-1.0.0-p0/`.
