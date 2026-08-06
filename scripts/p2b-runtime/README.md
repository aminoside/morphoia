# P2b Manifold auxiliary witness

This locked runtime is an auxiliary witness for P2a meshes classified `U`.
It does not prove solidity, does not change the primary status, and never emits
`V`. The only Manifold calls allowed by the profile are construction, status
inspection, and `getMesh()` for an exact topology-change check. No merge vector,
simplification, repair, Boolean operation, or MVX operation is permitted.
The pinned `manifold-3d@3.5.1` package declares the Apache-2.0 license; a full
transitive license audit remains a later release gate.

Install exactly the locked dependency with:

```sh
npm ci --ignore-scripts --omit=optional
```

The Python supervisor in `scripts/mvx_p2b_manifold_witness.py` binds each work
ID to the complete P2a plan/checkpoint chain and artifacts, source bytes,
canonical mesh, wrapper, lockfile, installed package metadata, Manifold
JavaScript/WASM, Node version and architecture, and the closed profile. The
wrapper imports the installed `manifold.js` file directly; package export maps
cannot redirect it. Child output goes to private size-limited regular files,
not unbounded captured pipes.
Object evidence remains in the ignored `tmp` tree and is published through an
atomic bundle before an immutable terminal checkpoint is written.
