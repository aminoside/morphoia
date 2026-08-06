# P2c exact triangle-contact diagnostics

P2c is an engineering diagnostic that checks exact contacts between triangles.
It is not part of the sealed P0 normative tree, does not certify a solid, and
does not grant gate credit. A result named
`EXACT_INTERSECTION_FREE_CANDIDATE` means only that this bounded oracle did not
find a forbidden contact under the recorded materialization policy and limits.

Campaign version, algorithm version, result-schema version, and Drive
checkpoint-schema version are separate identifiers. They must not be used
interchangeably.

## Campaign history

- `pilot3-2026-08-06-v1` is frozen as `UNANCHORED_DIAGNOSTIC`. Its four
  execution plans requested an external anchor, but no signed external anchor
  or signed readback receipt was produced. The terminal geometry and local
  authorization chains remain preserved at Git commit `63dadbf930be77a7281a564387e9b9cbf6082022`.
- P2c v2 is a new campaign. It must use new work identifiers, preserve original
  P2a vertex instances, use a persistent owner-controlled signer, and prove a
  clean restore before it can authorize idempotent reuse.

The public preregistration for that campaign is in
`preregistration/pilot3-2026-08-06-v2/`. It fixes the four execution slots,
resource profiles, index-preservation rule, authority claim boundary, clean
restore criterion, and scientific-projection comparison before any v2 result
exists.

The persistent signer is a continuity control, not an independent scientific
witness, not encryption, and not the G1 WORM publisher defined by the frozen P0
protocol.
