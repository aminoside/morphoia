# P2a source-only diagnostic — pilot 12

Date: 2026-08-06

Decision: **GO for continued source-ingestion engineering; G1 and every MVX round-trip claim remain blocked.**

## Scope

This is a deterministic, non-statistical engineering pilot over 12 private GLB sources. It validates only bounded source ingestion, Khronos validation, geometry materialisation, combinatorial topology evidence, immutable checkpoints, and exact restart behaviour.

It performs no MVX encoding, decoding, reconstruction, cohort selection, split assignment, source repair, external URI fetch, or neural-network experiment. The result is therefore not the protocol's `n12` MVX milestone.

## Results

| Measure | Result |
|---|---:|
| Sources | 12 |
| Exact source bytes | 57,296,652 |
| Fully materialised sources | 10 |
| Rejected sources | 2 |
| Materialised triangles | 693,555 |
| Positive non-manifold or invalid evidence (`N`) | 5 |
| Positive open-boundary evidence (`O`) | 2 |
| Unknown (`U`) | 5 |
| Verified solids (`V`) | 0 |
| External URI accesses | 0 |
| MVX operations | 0 |

Of the five `U` outcomes, three are closed edge-manifold candidates awaiting an independent solid verifier. The other two were not materialised: one requires a geometry extension outside the diagnostic profile, and one was rejected by the Khronos validator.

## Restart proof

The first campaign completed 12 immutable object terminals and one atomic campaign bundle. Repeating the exact command produced 12 object-level `SKIP` decisions and a campaign-level `SKIP`; no GLB was audited twice.

The source plan and all 12 content-addressed cache entries are hash-bound. A pristine-cache defect discovered before the campaign was reproduced by a regression test, corrected, and published before execution.

## Interpretation

The importer is sufficiently robust for a small diagnostic continuation, and it fails closed on unsupported or invalid inputs. The pilot also shows that arbitrary Objaverse GLB files cannot be treated as verified solids merely because they parse: half of the materialised sample has positive non-manifold or invalid evidence, while only three sources are even candidates for closed-solid verification.

Before any MVX round trip on natural objects, the next gate therefore requires:

1. an independent, pinned solid verifier;
2. an explicit policy for unsupported compressed geometry;
3. preservation of the present `O/N/U` evidence without source repair;
4. a separate, traceable normalisation path if repaired training assets are later desired.

Synthetic analytic fixtures may proceed in parallel because their ground truth does not depend on Objaverse source quality.

## Privacy

No Drive identifier, Objaverse UID, source title, source path, per-object source hash, work ID, or per-object measurement is present in this directory. Private manifests and object-level evidence remain outside Git.
