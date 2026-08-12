# P2c v2.1 public preregistration

Status: `FROZEN_BEFORE_EXECUTION`

Author: Dr Olivier Ami

This directory preregisters the rekeyed P2c campaign over the same private three
P2a parents and four resource profiles as the frozen v1 diagnostic. It contains
no v2.1 result, source identity, P2a work identifier, source hash, Drive
locator, signer manifest, signature, or private key. The signer manifest and
its public proof-of-possession signature are added only in the final public
precommit.

## Fixed scope

The private continuity manifest must prove that three P2a parents are exactly
the parents committed by the v1 terminal-evidence root. Three slots use the
default limit of 2,000,000 active broad-phase comparisons. A fourth slot uses
10,000,000 comparisons and is linked to the same private parent as the v1
default execution that reached the pair limit. The aliases `PARENT_A` through
`PARENT_C` are opaque campaign labels, not published source identifiers.

The campaign version is `2.1.0`. It supersedes v2.0, which was aborted before
execution after confidentiality of its signer secret was lost. It is
deliberately distinct from algorithm
version `0.3.0`, result-schema version `0.3.0`, materializer version `0.2.0`,
and Drive checkpoint-schema version `2.3.0`.

The runner work identifier directly hashes the execution-plan fields, including
the algorithm identity, code hash, runtime, P2a input binding, limits, source
binding, authority policy, and persistent public key. Campaign identity,
preregistration, result-schema version, and the declared vertex-index policy are
instead bound by the private pre-execution freeze and continuity manifest. The
result schema and vertex policy are also implemented by the runner captured by
the plan's code hash. This distinction is explicit: the campaign metadata is
not falsely described as a direct field of the runner work identifier.

## Scientific correction

The v2 materializer must preserve the P2a materialized vertex-instance array
and every triangle index. It may normalize the numeric value negative zero to
positive zero, but it may not merge, reorder, deduplicate, or remap vertices or
triangles. Consequently, v2 is allowed to find a contact that v1 missed after
coordinate-equal vertex instances were welded. Such a difference is a
scientific result, not an envelope mismatch.

## Authority boundary

The campaign uses a persistent owner-controlled signer. The signer supports
continuity and exact restart verification only. It is not independent, not a
write-once-read-many (WORM) publisher, not encryption, not a solid verifier,
and not the G1 custodian. Loss or replacement of its key invalidates anchored
reuse and requires a newly versioned campaign; it never permits silently
changing this preregistration.

The private signing seed may be retained as two owner-only Google Drive files
in two distinct folders of the same account. Those copies improve restart
continuity but remain one administrative failure domain. Drive permissions,
revision identifiers, and downloaded-byte checks are caller/API observations,
not cryptographic proof of Drive origin or immutability. The signing seed is
not an encryption key and is never included in Git, public results, or a P2c
result bundle.

## Publication order

The committed code, this preregistration, its projection contexts, and the
public signer manifest must be published to the designated GitHub branch before
any v2 plan is frozen or geometry child is started. A local-only commit or a
private Drive copy does not satisfy that public-preregistration condition.
After publication, the four plans are derived without starting a child, the
private continuity manifest is signed, and only then may the first v2 child
execute.

The official runner enforces this split with `prepare-p2a-plan` followed by
`execute-prepared-p2a`. The preparation command requires the immutable private
prefreeze bundle and writes one exact plan without invoking the exact-analysis
child. A first anchored `run-p2a` invocation is rejected. The execution command
requires the same prefreeze bundle, the exact prepared plan, the private
continuity manifest, and its detached Ed25519 authentication; it validates all
four bindings before the child can start.

## Restore and comparison

Completion requires a clean restoration into a new workspace from the frozen
code and verified private checkpoint. File bytes, required file modes, empty
directories, checkpoint chain, completion marker, latest pointer, signed
anchor, and signed readback receipt must all validate before the restored run
may return `SKIP_ANCHORED`. Access to the original run directory is forbidden
during that test.

Complete execution envelopes are not compared across campaigns. The utility
`scripts/mvx_p2c_scientific_projection.py` projects only preregistered
scientific fields and excludes work identifiers, source identifiers, plan and
checkpoint hashes, paths, locators, authority claims, keys, and signatures.
Per-slot projections remain private because mesh counts and contact witnesses
may fingerprint a private source. Only an aggregate and its commitment may be
published after execution.

Projection is fail-closed. Both the v2 and historical-v1 commands require the
private prefreeze bundle, continuity manifest, detached continuity
authentication, exact execution plan, terminal checkpoint, authority claim,
and result. The detached signature is validated before projection, and each
private projection records commitments to those three continuity artifacts.
Comparison requires both projections to carry the same validated commitments.
The manifest binds each opaque slot to both its v1 and v2 work identities and
to the same sealed P2a parent. A caller cannot assign a result to a slot merely
by naming that slot or by substituting an unsigned continuity manifest.

The projection utility never writes a private projection or comparison to
standard output. Its output must be a new file below `tmp/`, published
atomically with mode `0600`; an existing destination is never overwritten.

The private continuity manifest uses schema
`MVX-P2C-PRIVATE-CAMPAIGN-CONTINUITY` version `1.0.0`. Its top level binds the
campaign ID, frozen preregistration value hash, v1 terminal-evidence root, and
the persistent signer public key, plus exactly four ordered `slots`. Each slot
repeats the public slot ID, comparison slot, opaque parent alias, profile and
pair limit. Its `v1` and `v2` members each contain exactly
`execution_plan_sha256`, `source_sha256`,
`p2a_execution_plan_sha256`, `p2a_terminal_checkpoint_sha256`, `p2a_work_id`,
and `work_id`. The v1/v2 parent bindings must match while their work IDs and
execution-plan hashes must remain distinct. This manifest is created only
after all four v2 plans have been derived and before the first v2 child runs.

No P2c v2.1 outcome can emit `V`, certify a solid, satisfy G1, or receive any
other gate credit. A separate independent solid verifier remains mandatory.
