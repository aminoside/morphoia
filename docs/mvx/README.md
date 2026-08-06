# Morphoia Visual Exchange (MVX)

MVX is the derived 3D-to-multiview representation studied by Morphoia. It does
not replace the canonical Morphoia construction graph, STEP AP242, or the
source mesh. The current work is a feasibility programme for a stable MVX 1.0
Core.

## Authoritative documents

- `specification/MORPHOIA_MVX_Rapport_de_proposition_technique_v0.2.pdf`
- `specification/MORPHOIA_MVX_Addendum_Implementation_v0.2.1.pdf`
- `validation/MORPHOIA_MVX_Plan_experimental_complet_vers_v1.pdf`

## Validation status

Phase P0.1 freezes the confirmatory protocol before cohort selection or metric
inspection. P1a metadata census and P2a source-only ingestion audit may precede
G1 because they do not inspect MVX outcomes. The machine-readable package is in
`validation/p0/`. Run:

```bash
morphoia mvx protocol verify
morphoia mvx custody dry-run
```

No MVX 0.3 or 1.0 claim is made by the P0 package. After G0 it authorises only
the P1a census and P2a source-only audit. G1 selection remains blocked until an
external custody boundary has sealed the eligible-record root, generated fresh
selection/split secrets and published the dual-secret precommit before use.
The freeze also requires a signed immutable-store publication receipt from a
production publisher key frozen in the protocol; no such production key is
authorised at G0, so G1 remains deliberately blocked pending provisioning.

All later compute is resumed through immutable execution plans and stage
checkpoints. Terminal artifacts are skipped only after their hashes are
revalidated; incomplete ordinary work is retried, while interrupted blind
open-once work fails closed.
