# MVX validation backup and resume contract

This operational contract applies to every P0--P13 validation run. It is not a
substitute for the frozen P0 protocol; it defines how implementation state and
results survive a reset without silently repeating completed work.

## Durable copies

Every accepted gate and every long-running campaign checkpoint has two durable
copies:

1. a dedicated GitHub branch containing public source, schemas, tests,
   aggregate results and reproducibility metadata; and
2. a private Google Drive checkpoint containing the public bundle plus private
   operational inputs that must not enter the public repository.

Production selection seeds, split salts, blind identities and mappings are
never stored in plaintext in either destination. The custody area accepts only
ciphertext whose decryption key is held outside the development workspace and
outside Google Drive.

## Checkpoint identity

The checkpoint identifier is derived from the phase, gate, Git commit and
frozen protocol root. Its registry records at least:

- Git repository, branch and immutable commit SHA;
- protocol ID, version and root SHA-256;
- source snapshot and split commitments when they exist;
- execution-plan and terminal stage-checkpoint hashes;
- hashes and byte sizes of every uploaded artifact;
- test, verifier and gate verdict summaries;
- predecessor checkpoint ID and creation time.

`LATEST.json` may reference a checkpoint only after every listed object has
been fetched or inspected and its byte size and SHA-256 have been verified.
`COMPLETED.json` is written last. A directory without that terminal marker is
an interrupted staging attempt, never an accepted checkpoint.

## Resume decision

After a reset, the worker must load `LATEST.json`, verify the terminal marker,
restore the exact Git commit and validate the stage checkpoint chain before it
opens any source object.

- A hash-valid terminal `COMPLETED`, `PASS`, `FAIL`, `REJECT` or
  `DECLARED_LIMIT` checkpoint is skipped.
- A non-blind idempotent stage with a valid persisted claim may be retried and
  must preserve attempt lineage.
- A blind or `open_once` stage without an intact authoritative claim fails
  closed; it is never silently replayed.
- A changed protocol root, source/split commitment, profile, code, environment
  or configuration creates a different `work_id`; it cannot reuse an older
  terminal result.
- A conflicting checkpoint, manifest mismatch, symlink, hidden artifact or
  partial bundle blocks execution and is quarantined for audit.

## Cadence

Create a checkpoint at every gate, before and after each campaign expected to
run longer than one hour, after each result shard, and before any environment
handoff. GitHub publication precedes the Drive terminal marker so the registry
can bind the immutable commit. Results are never considered durable until both
copies and their verification evidence exist.
