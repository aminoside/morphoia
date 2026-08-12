# ExecPlan operating rules

<!-- SPDX-License-Identifier: CC-BY-4.0 -->

`docs/engine/EXECUTION_PLAN.md` is the durable, self-contained plan for the
current Morphoia Engine milestone. An agent must be able to resume from it and
`docs/engine/checkpoint.json` without relying on chat history.

## Required content

Keep the ExecPlan current with:

- objective, scope, anti-scope, and source-of-truth baseline;
- current phase, lot, branch, and integration target;
- finite milestones with acceptance criteria and exact validation commands;
- completed, active, and remaining work;
- decisions and ADR links;
- surprises and deviations;
- commands actually run and their honest results;
- evidence locations and hashes when available;
- external dependencies and profile-specific blockers;
- exactly one idempotent next action;
- clean-room and post-reset recovery steps.

## Editing protocol

Update the plan before starting a new milestone, after discovering a material
constraint, after every gate attempt, and before a checkpoint commit. Do not
rewrite prior results to make the current state appear cleaner. Date material
updates and distinguish observations from proposals.

Keep work bounded. A phase may contain only tasks already listed in the current
plan. Adding scope requires an explicit plan revision and, for a structural
choice, an ADR. After E6, execute only the frozen `E9-INDEPENDENT` slice in
`docs/engine/E9_INDEPENDENT.md`; do not grow it opportunistically.

## Long-running and restartable work

For every nontrivial experiment derive an operation key from code, input,
configuration, dependency versions, and seeds. Write outputs atomically, then
write a success marker and manifest. Before rerunning, validate the marker and
all recorded hashes. Resume only missing or invalid outputs.

Before automatic resource approval, the hard limits in
`docs/engine/RESOURCE_BUDGET.yaml` apply: no single download over 2 GiB, no job
over 60 minutes, and no operation consuming more than 70 percent of free disk.

## Gate protocol

For a gate attempt:

1. freeze inputs, versions, environment, and criteria;
2. run the documented commands;
3. retain raw evidence and a compact report;
4. classify every applicable item with the five permitted evidence statuses;
5. fix and rerun only affected checks;
6. after three reasonable failed approaches, record the blocker and fallback;
7. integrate and tag only when mandatory checks for the declared profile pass.

Operational pre-releases do not imply contractual G1-G5 completion.
