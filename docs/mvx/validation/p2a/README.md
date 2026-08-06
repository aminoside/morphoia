# P2a — diagnostic source-only GLB

This package runs the pre-G1 engineering diagnostic used to inspect a small,
deterministically ranked prefix of the private Objaverse snapshot. It is not
the protocol `n12` milestone, does not create a cohort or split, and performs
no MVX encoding, decoding, reconstruction, or model training.

## Safety boundary

- The default scope is 12 independent UIDs selected by the frozen public
  bootstrap HMAC order. `--count N` selects a longer prefix of the same order.
- Per-object work IDs exclude the scope ordinal and campaign size. Completed
  work is therefore reused unchanged when the scope grows from 12 to N.
- Source membership, Drive IDs, UIDs, source hashes, object metrics, and work
  IDs remain under the ignored private `tmp/` tree.
- The public campaign summary contains only aggregate counts and commitments.
- External URI resolution and all MVX operations are forbidden.
- The locked Khronos glTF Validator must report zero errors before the stdlib
  geometry scanner runs.
- The scanner can emit only `O`, `N`, or `U`; it never emits `V` without an
  independent solid verifier.
- G1, eligibility, complexity quantiles, and split assignment remain blocked.

## Locked runtime

Install the validator exactly from the committed npm lock before execution:

```bash
npm --cache /tmp/morphoia-npm-cache \
  --userconfig /dev/null \
  ci --ignore-scripts --audit=false --fund=false \
  --prefix scripts/p2a-runtime
```

The runner binds its work identity to the Python source closure, the wrapper,
the npm manifests, the Python/Node executables, and the installed validator
files. A missing, dirty, or mismatched execution closure fails closed.

## Workflow

1. Freeze a private HMAC prefix without reading source geometry:

   ```bash
   .venv/bin/python scripts/mvx_p2a_checkpoint.py make-pilot \
     --snapshot tmp/p1/objaverse-live.json \
     --snapshot-sha256 SNAPSHOT_SHA256 \
     --count 12 \
     --output tmp/p2a/pilot-12.json
   ```

2. Materialize exactly the named private files into
   `tmp/p2a/incoming/source-NNNN.glb`, then seal them into the content-addressed
   cache:

   ```bash
   .venv/bin/python scripts/mvx_p2a_checkpoint.py seal-sources \
     --pilot-plan tmp/p2a/pilot-12.json \
     --pilot-plan-sha256 PILOT_PLAN_SHA256 \
     --incoming tmp/p2a/incoming \
     --cache-root tmp/p2a/cache \
     --output tmp/p2a/audit-plan-12.json
   ```

3. Run the isolated audit:

   ```bash
   .venv/bin/python scripts/mvx_p2a_checkpoint.py run \
     --audit-plan tmp/p2a/audit-plan-12.json \
     --audit-plan-sha256 AUDIT_PLAN_SHA256 \
     --cache-root tmp/p2a/cache \
     --run-root tmp/p2a/runs
   ```

4. Invoke the same command again. It must return `SKIP` for every verified
   terminal object and for the completed campaign.

## Restart contract

Each object has an immutable, hash-linked checkpoint chain and an atomic
artifact bundle. A reset can replay only an unfinished object; a verified
terminal object is skipped. A child crash is persisted as `MVX-X002`, and no
more than two attempts are permitted. Partial object and campaign staging
directories are moved to quarantine, never silently deleted.

The campaign marker binds its private manifest, public summary, terminal set,
aggregate evidence, code identity, and environment. Duplicate work IDs,
forged transitions, terminal/audit disagreement, private-token leakage, and
partial or extra files fail closed.

## Known diagnostic limits

The stdlib scanner detects edge and vertex non-manifoldness, boundaries,
orientation conflicts, duplicate and degenerate triangles, and connected
components. It does not provide robust geometric self-intersection testing or
solid certification. Those capabilities require the later locked geometry
toolchain and an independent verifier before G1.
