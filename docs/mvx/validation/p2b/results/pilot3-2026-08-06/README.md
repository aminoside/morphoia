# P2b pilot — locked Manifold auxiliary witness

This three-object micro-campaign is a bounded, restart-safe diagnostic performed
only on the fully materialised closed candidates that remained `U` after P2a.
The candidate identities, source hashes, object-level evidence and paths remain
private.

All three canonical meshes were accepted by the locked `manifold-3d@3.5.1`
runtime with `NoError`, unchanged vertex and triangle counts, and unchanged
topology hashes. A second identical invocation returned `SKIP` for all three
objects, so no completed work was recomputed.

This result is **not a solidity proof**. The witness never emits `V` and never
changes the primary P2a status `U`. Adversarial fixtures demonstrate that
closed interpenetrating shells can also be corroborated by Manifold. Exact
triangle-intersection testing therefore remains a separate required stage.

The machine-readable aggregate and the commitment to the private evidence set
are in `public-summary.json`.
