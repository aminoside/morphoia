# Thread safety

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

This document is the exhaustive thread-safety contract for the proposed
`engine-ir-core-si-0.1` qualification and inspection profile. It implements
the documentation side of `MOR-API-006`; it does not prove the behavior. The
requirement and this profile remain `NOT_RUN` until the inventory, concurrency,
lifetime, sanitizer, and hosted tests described below execute successfully.

This profile includes the exact eight-symbol C ABI, its reference
`NativeEngine` wrapper, the public Engine IR 0.1 validation/replay functions
used by inspection, the new high-level inspection function, and the CLI
families named below. Legacy prototype construction-graph APIs, optional
SALOME protocol objects, CAS internals, and future domain/GPU/HPC/MVX backends
are outside this profile and retain `NOT_RUN` thread-safety status.

## Terms and global rules

| Term | Meaning |
|---|---|
| Reentrant | Separate calls use no mutable shared library state and may overlap when caller-owned storage is disjoint. |
| Same-context read-only | Calls may overlap on one live `morphoia_context_t`; the caller must keep the context alive and serialize destruction. |
| Serialized by wrapper | `NativeEngine` holds one per-instance reentrant lock across a native call and across close; calls are safe but do not run in parallel on that instance. |
| Caller-serialized | Concurrent use is unsupported unless the caller provides a lock covering the complete documented operation and lifetime. |
| Separate process | Independent CLI invocations may overlap because they do not share Python objects, file descriptors, or standard streams. |

The following rules apply to every family in this profile:

- Every caller-owned mutable output, diagnostic, and temporary buffer used by
  overlapping calls must be disjoint. Sharing the same output or diagnostic is
  a data race even when inputs are identical.
- Shared input bytes may be read concurrently only while immutable and alive
  for every call. The API retains no input pointer after return.
- A `morphoia_context_t` remains valid from successful creation until the one
  destroying call consumes it. Destruction is exclusive: no copied alias may
  be used, and no same-context call may start or remain active once destruction
  begins.
- A caller-provided allocator and its `user_data` must be safe for every
  creation/destruction concurrency pattern chosen by that caller. Callbacks
  must not throw, reenter, or recursively destroy the same context.
- The native unit qualification and canonicalization operations do not allocate
  through the context allocator.
- Thread safety does not make semantically conflicting filesystem operations
  acceptable. Workspace rules below remain authoritative.

## Native C ABI inventory

This table contains every symbol permitted by the profile's exact export
allowlist. An inventory test must fail if an export is missing, added, or left
undocumented here.

| C symbol | Shared state and ownership | Concurrency contract | Forbidden overlap |
|---|---|---|---|
| `morphoia_engine_get_version` | No context; writes caller-owned version and diagnostic; returned string view has static storage duration. | Reentrant across threads with disjoint outputs. | The version prefix and diagnostic prefix must not be concurrently shared or mutated. |
| `morphoia_status_name` | No context; returns immutable static storage. | Reentrant; the same returned view may be read concurrently. | Callers must not write through the returned view. |
| `morphoia_context_create` | Creates one caller-owned opaque handle; may invoke the selected allocator. | Concurrent creation of distinct contexts is allowed when each output/diagnostic is disjoint and the allocator is safe for the chosen concurrency. | The same handle output, options being mutated, diagnostic, or non-thread-safe allocator state must not be shared concurrently. |
| `morphoia_context_destroy` | Immediately consumes `*context`, clears it, then invokes its deallocator. | Caller-serialized and exclusive for that handle. Destroying null is idempotent only for that pointer value, not permission to race aliases. | Any same-context call, second destroy through an alias, or allocator callback reentry during destruction. |
| `morphoia_context_get_abi_version` | Reads one live context; writes caller-owned integer and diagnostic. | Same-context read-only with disjoint outputs and destruction serialized. | Shared ABI output/diagnostic or concurrent destroy. |
| `morphoia_context_query_capability` | Reads one live context and borrowed capability bytes; writes caller-owned result/diagnostic; returned views use immutable static storage. | Same-context read-only. Multiple capability queries and other read-only calls may overlap with disjoint storage. | Context, capability bytes, output prefix, and diagnostic prefix must meet the ABI alias rules; concurrent destroy is forbidden. |
| `morphoia_canonical_json_profile1` | Reads one live context, explicit-length input, and optional limits; writes caller-owned output, size, digest, and diagnostic. | Same-context read-only. Calls may overlap when all input/output/option/diagnostic storage follows the ABI disjointness rules. | Concurrent destroy; mutable shared input; shared output, required-size, digest, options, or diagnostic; cross-call overlapping writable buffers. |
| `morphoia_context_validate_engine_ir_unit` | Reads one live context, sized input unit, and explicit-length code; atomically writes caller-owned verdict and diagnostic. | Same-context read-only. Unit calls may overlap each other and capability/canonicalization calls when storage is disjoint. | Concurrent destroy; mutation of shared unit/code bytes; shared verdict/diagnostic; any alias prohibited by the ABI contract. |

The native same-context claims above are Proposed until tests exercise all
read-only combinations, close/destroy exclusion, distinct contexts, disjoint
and adversarial overlapping buffers, allocator callbacks, and failure
atomicity under ASan and UBSan. A successful single-thread test is not
thread-safety evidence.

## Reference Python native wrapper inventory

`NativeEngine` owns one native context and one per-instance `threading.RLock`.
The lock spans each public native operation and `close()`. This makes those
operations on a single wrapper instance safe by serialization, not parallel.
The `closed` snapshot and context-manager entry are not lifetime leases; their
restrictions are explicit below. Different instances have different locks and
may execute concurrently, subject to native library and caller input rules.

| Python surface | Contract on one instance | Cross-instance contract | Ownership and close behavior |
|---|---|---|---|
| `resolve_native_library(explicit_path=None)` | Reentrant while the dedicated environment variable and installed-library state remain unchanged. | Calls may overlap, but changing process environment or library installation concurrently is unsupported. | Returns a path string only; it does not load or own a library. |
| `NativeEngine(...)` | Construction is not observable until complete. Do not publish a partially constructed instance. | Distinct instances may be constructed concurrently. | Each successful instance owns exactly one native context and loaded-library handle. |
| `NativeEngine.__enter__` / `__exit__` | Entry checks liveness but is not a lease; callers must not race entry with close or enter the same instance concurrently. Exit calls serialized `close()`. | Independent instances may use independent context managers. | `__exit__` closes only its instance. |
| `NativeEngine.closed` | An observational snapshot only. If the result will govern later use, the caller must serialize that larger check-and-use sequence; false cannot authorize an unlocked later call. | Independent across instances. | Prefer calling the locked operation and handling its stable closed-context error. |
| `NativeEngine.close()` | Serialized and idempotent on the instance. It waits for the current locked call, prevents a later call from using a consumed context, and may be invoked by one thread while another finishes a call. | Distinct instances close independently. | After return, the instance is closed; caller-supplied aliases must not bypass the wrapper. |
| `NativeEngine.query_capability(name)` | Serialized by the instance lock. | May run concurrently on different instances. | Input is copied/borrowed only for the call; returned dataclass is caller-owned. |
| `NativeEngine.canonicalize(source, *, limits=None)` | Both native passes are one locked operation; `close()` cannot interleave between measurement and output. | May run concurrently on different instances and immutable/disjoint inputs. | Returned bytes/dataclass are caller-owned; no fallback implementation is used. |
| `NativeEngine.validate_engine_ir_unit(code, *, dimensions, si_factor_coefficient, si_factor_scale)` | One locked, atomic unit qualification operation; `close()` cannot interleave. | May run concurrently on different instances. | Arguments are converted to call-local native storage; returned verdict is caller-owned. |
| `NativeEngine.version`, `library_path`, `library_file`, `library_sha256`, and `capability` | Concurrent reads after successful construction are allowed. | Independent instances hold independent Python attributes. | These are read-only by contract; caller mutation or replacement is unsupported. |
| Native wrapper constants, immutable result dataclasses, and exception types | Concurrent reads are reentrant. | Values are process-wide immutable definitions or caller-owned results. | Callers must not mutate nested values or ctypes-private implementation objects. |

The exact unit-wrapper signature and behavior are Proposed and `NOT_RUN` until
implemented. The Python lifetime gate must race repeated capability,
canonicalization, and unit calls against `close()` without use-after-free,
double destroy, partial two-pass output, or deadlock. The expected result is a
completed call or a stable closed-context error, never undefined behavior.

## Public Engine IR and inspection Python inventory

These functions operate on caller-owned values. They are reentrant when their
inputs remain immutable and every filesystem output is distinct. Any supplied
`NativeEngine` follows the wrapper serialization above.

| Python surface or family | Thread-safety contract | Filesystem or ownership boundary |
|---|---|---|
| `seal_content(content, *, engine, limits=None)` | Reentrant for immutable/caller-isolated content; calls sharing one engine serialize. | Does not mutate `content`; returned manifest/bytes are caller-owned. |
| `validate_manifest(source, *, engine, limits=None)` and public alias `validate_engine_ir_manifest` | Reentrant for immutable source; calls sharing one engine serialize. | Does not resolve payload references or mutate input. |
| `migrate_legacy_manifest(legacy_document, *, metadata, engine, limits=None)` | Reentrant for immutable legacy bytes and metadata; calls sharing one engine serialize. | Does not mutate legacy bytes; returned manifest is caller-owned. |
| `create_replay_recipe(manifest, *, seed=0, expected_runs=2)` | Reentrant for an immutable `ValidatedManifest`. | Pure construction; returned mapping is caller-owned. |
| `read_bounded_file(path, maximum_bytes=...)` | Concurrent reads are allowed only when the file and directory metadata remain stable. | Each call owns its descriptors; mutation is rejected. It does not establish a reusable file lease. |
| `resolve_manifest_reference(recipe, path)` | Reentrant for immutable recipe and stable file. | Each call snapshots and verifies independently. |
| `replay_manifest(..., workspace_root, engine, ...)` | Calls sharing an engine serialize their native steps. Distinct engines may overlap. Cancellation events may be set from another thread. | Same operation key plus identical checkpoint bytes is idempotent on the declared Linux/POSIX profile. Conflicting bytes, unsafe metadata, symlinks, aliases, or nonprivate workspace state fail. Use distinct workspaces for unrelated operations when possible. |
| `inspect_engine_ir(source, *, profile="engine-ir-core-si-0.1", engine=None)` | Reentrant for immutable source. A supplied engine serializes all native work; with `engine=None`, each call owns an independent wrapper/context. | A supplied engine remains caller-owned and is not closed. An internally created engine is closed before return. Inspection performs no payload access and creates no workspace output. |
| `load_json_strict`, contract `validate_manifest`, and contract `validate_replay` | Reentrant for caller-owned or immutable inputs. | They allocate and return call-local Python objects and do not resolve files except schema discovery documented by the installed package. |
| `build_legacy_migration_content` | Reentrant for immutable caller inputs. | No file write and no mutation of source bytes. |
| Engine IR/inspection constants, immutable result dataclasses, and exception types | Concurrent reads are reentrant. | Values are process-wide immutable definitions or caller-owned results. Treat mappings contained in results as read-only. |

Schema resolution and the cached schema/validator objects used by validation
and inspection are read-only after construction. Concurrent calls require the
installed schema files to remain stable; replacing or editing a schema while a
process is validating is unsupported. Reentrancy of the shared cache and
validator path is part of the required Python concurrency gate, not an assumed
library guarantee.

`ValidatedManifest`, `ReplayResult`, the proposed `EngineIrInspection`,
capability records, limits, and unit-verdict result objects are immutable value
objects after construction. Contained mappings must be treated as read-only by
callers; immutability of a dataclass does not recursively freeze a mutable
mapping supplied by untrusted code.

The public `src/morphoia/__init__.py` also exports legacy prototype APIs
(`canonical_json`, `compile_document`, `semantic_hash`, `parse`,
`RuntimeStore`, `validate_file`, and `validate_source`). They are not members
of `engine-ir-core-si-0.1`. In particular, `RuntimeStore` and its transactions
have mutable history and no internal lock; all operations on one store are
caller-serialized. Their thread-safety remains `NOT_RUN` and cannot be used to
promote this profile's `MOR-API-006` result beyond the declared Engine APIs.

## CLI inventory

| CLI family | Concurrent-use contract | Shared-process restriction |
|---|---|---|
| `morphoia inspect MANIFEST [--json]` | Separate OS processes may inspect the same stable read-only manifest concurrently. Each process owns its native context. | Concurrent calls to `cli.main()` inside one Python process are unsupported because argument parsing and standard output/error are process-global streams. |
| `morphoia engine-ir validate` | Separate processes may validate the same stable read-only manifest concurrently. | Same in-process `main()` restriction. |
| `morphoia engine-ir replay` | Separate processes may share an operation key only under the identical atomic checkpoint rule; conflicting bytes fail. Distinct private workspaces are preferred. | Same in-process `main()` restriction; workspace safety rules still apply. |

The legacy `morphoia validate` and `morphoia compile` commands are outside the
qualified inspection profile. `compile` writes a caller-selected output path
without a cross-process transaction contract and must not be run concurrently
against the same output. Their general thread/process safety remains
`NOT_RUN`.

CLI exit codes do not communicate scheduling or cancellation. For inspection,
0 means completed qualified inspection, 1 means an input/profile/runtime/
contract/qualification rejection, and 2 means argument-parser rejection.
Concurrent process results must be evaluated independently.

## Excluded API families

The following are deliberately excluded and receive no thread-safety claim
from this document:

- the mutable legacy `RuntimeStore`, transaction, compiler, parser, and source
  validation prototype families except for the caution above;
- internal Profile 1 parser, SHA-256, and POSIX CAS C++ classes, which are not
  installed public APIs;
- `FakeSalomeAgent` and the E2 protocol implementation, which have a separate
  contract-only evidence boundary and no real SALOME runtime claim;
- OCCT/XDE, VTK, ITK, PDAL, MED/MEDCoupling, SHAPER/GEOM, SMESH, YACS,
  JOBMANAGER, Kokkos, PETSc, MFEM, DLPack, Arrow, PyTorch, ONNX Runtime, CUDA,
  HIP, SYCL, Slurm, and EuroHPC integrations; and
- any MVX codec, reconstruction, corpus, or scientific evaluation API.

An excluded family remains `NOT_RUN` even if it happens to call a documented
thread-safe primitive. It must receive its own exhaustive inventory and
executed evidence before a compatibility claim.

## Required evidence before promotion

`MOR-API-006` may become `PASS` only for this named profile after all of the
following succeed and are hash-addressed:

1. an automated inventory proves that all eight and only eight C exports, all
   profile Python public functions/methods, and all profile CLI commands occur
   in this document;
2. native tests overlap capability, canonicalization, ABI query, and unit
   qualification on one context and on distinct contexts with disjoint
   storage, then verify that destruction is excluded;
3. adversarial native tests cover shared diagnostics/outputs, partial aliases,
   ABI prefixes, larger structures, failure atomicity, callback success,
   rejection, alignment, exception containment, and one caller-synchronized
   allocator shared by demonstrably overlapping distinct-context operations;
   prohibited recursive callback reentry remains an explicit caller
   precondition and is not invoked as if undefined caller behavior were a
   supported operation;
4. Python tests race calls against `close()`, exercise one-instance
   serialization and distinct-instance concurrency, and detect deadlocks with
   bounded timeouts;
5. replay tests cover identical and conflicting concurrent checkpoint writers,
   unsafe workspace metadata, symlinks, and input mutation;
6. CLI process tests cover deterministic concurrent read-only inspection and
   stable human/JSON/exit-code behavior without mixed-stream assumptions;
7. two clean builds, the installed C consumer, ASan, UBSan, Python 3.12,
   Python 3.13, full regression, and required hosted branch/PR checks pass.

Until every item passes, this matrix is a Proposed contract and the profile's
`MOR-API-006` status is `NOT_RUN`. A skipped platform, mock, code inspection,
or compilation-only result does not satisfy the gate.
