"""Deterministic grouped split implementation for MVX P0."""

from __future__ import annotations

import copy
import hashlib
import math
from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from .custody import canonical_json_bytes
from .hmac_rank import hmac_sha256_rank

SPLITS = ("development", "calibration", "blind")
ALGORITHM_ID = "MVX-GROUP-STRATIFIED-HMAC-2"
ALGORITHM_VERSION = "2.0.0"
DIMENSIONS = (
    "selection_stratum",
    "dataset",
    "topology_status",
    "complexity_quantile",
    "category",
)


def _hmac_hex(salt: bytes, domain: str, *parts: str) -> str:
    return hmac_sha256_rank(
        salt,
        algorithm_id=ALGORITHM_ID,
        algorithm_version=ALGORITHM_VERSION,
        domain=domain,
        parts=parts,
    ).hex()


def _largest_remainder(total: int, ratios: dict[str, float]) -> dict[str, int]:
    raw = {name: total * ratios[name] for name in SPLITS}
    result = {name: math.floor(raw[name]) for name in SPLITS}
    remaining = total - sum(result.values())
    order = sorted(SPLITS, key=lambda name: (-(raw[name] - result[name]), SPLITS.index(name)))
    for name in order[:remaining]:
        result[name] += 1
    return result


def _normalise_cell(value: Any) -> str:
    return "<NULL>" if value is None else str(value)


def _implementation_sha256() -> str:
    return hashlib.sha256(Path(__file__).read_bytes()).hexdigest()


def _commitment_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Encode an optional bbox exactly inside the no-float split commitment."""

    committed = copy.deepcopy(dict(row))
    bbox = committed.pop("bbox", None)
    if bbox is None:
        return committed
    if not isinstance(bbox, (list, tuple)) or len(bbox) != 6:
        raise ValueError("bbox must contain exactly six finite numbers")
    encoded: list[str] = []
    for value in bbox:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("bbox must contain exactly six finite numbers")
        try:
            number = float(value)
        except OverflowError as error:
            raise ValueError("bbox contains a non-binary64 coordinate") from error
        if not math.isfinite(number):
            raise ValueError("bbox must contain only finite numbers")
        if isinstance(value, int) and int(number) != value:
            raise ValueError("bbox integer is not exactly representable as binary64")
        encoded.append(number.hex())
    committed["bbox_binary64_hex"] = encoded
    return committed


def _forced_aware_targets(
    rows: Iterable[dict[str, Any]],
    *,
    dimension: str,
    ratios: Mapping[str, float],
    honor_forced: bool = False,
) -> dict[str, dict[str, int]]:
    """Build secondary-cell targets while preserving declared reservations."""

    totals: Counter[str] = Counter()
    forced: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        cell = _normalise_cell(row[dimension])
        totals[cell] += 1
        forced_split = row.get("forced_split")
        if honor_forced and forced_split:
            forced[cell][str(forced_split)] += 1
    targets: dict[str, dict[str, int]] = {}
    ratio_dict = {name: float(ratios[name]) for name in SPLITS}
    for cell, total in totals.items():
        forced_count = sum(forced[cell].values())
        unforced = total - forced_count
        allocated = _largest_remainder(unforced, ratio_dict)
        targets[cell] = {
            name: allocated[name] + forced[cell][name]
            for name in SPLITS
        }
    return targets


def _secondary_balance_limit(*, dimension: str, target: int, largest_group: int) -> int:
    """Return the frozen absolute discrepancy bound for one secondary cell."""

    if dimension == "selection_stratum":
        return 0
    fraction = 0.20 if dimension == "category" else 0.10
    return max(largest_group, 2, math.ceil(fraction * max(1, target)))


def assign_grouped_split(
    records: Iterable[dict[str, Any]],
    *,
    salt_hex: str,
    ratios: dict[str, float] | None = None,
    weights: dict[str, float] | None = None,
    exact_targets_by_stratum: Mapping[str, Mapping[str, int]] | None = None,
) -> dict[str, str]:
    """Assign complete leakage groups without consulting experimental outcomes."""

    ratios = ratios or {"development": 0.5, "calibration": 0.2, "blind": 0.3}
    weights = weights or {
        "total_count": 100.0,
        "selection_stratum": 40.0,
        "dataset": 20.0,
        "topology_status": 10.0,
        "complexity_quantile": 5.0,
        "category": 1.0,
    }
    if set(ratios) != set(SPLITS) or not math.isclose(sum(ratios.values()), 1.0):
        raise ValueError("ratios must define development/calibration/blind and sum to one")
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError as error:
        raise ValueError("salt_hex must be hexadecimal") from error
    if len(salt) != 32:
        raise ValueError("salt_hex must encode 256 bits")

    rows = [dict(record) for record in records]
    if not rows:
        return {}
    required = {
        "lineage_id",
        "leakage_group_id",
        "creator_group",
        "source_uid",
        "eligibility",
        *DIMENSIONS,
    }
    seen_lineages: dict[str, str] = {}
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        missing = required - set(row)
        if missing:
            raise ValueError(f"split record missing fields: {sorted(missing)}")
        lineage = str(row["lineage_id"])
        group = str(row["leakage_group_id"])
        if not lineage or not group or not str(row["selection_stratum"]):
            raise ValueError("lineage_id, leakage_group_id and selection_stratum must be non-empty")
        if row["eligibility"] != "ELIGIBLE":
            raise ValueError(f"lineage {lineage!r} is not ELIGIBLE for split assignment")
        if lineage in seen_lineages:
            raise ValueError(f"lineage {lineage!r} occurs more than once")
        seen_lineages[lineage] = group
        groups[group].append(row)

    total_targets = _largest_remainder(len(rows), ratios)
    cell_totals: dict[str, Counter[str]] = {dimension: Counter() for dimension in DIMENSIONS}
    for row in rows:
        for dimension in DIMENSIONS:
            cell_totals[dimension][_normalise_cell(row[dimension])] += 1
    cell_targets: dict[str, dict[str, dict[str, int]]] = {dimension: {} for dimension in DIMENSIONS}
    for dimension, cells in cell_totals.items():
        for cell, count in cells.items():
            cell_targets[dimension][cell] = _largest_remainder(count, ratios)

    counts_total = Counter({name: 0 for name in SPLITS})
    counts_cells: dict[str, dict[str, Counter[str]]] = {
        dimension: {name: Counter() for name in SPLITS} for dimension in DIMENSIONS
    }
    group_assignment: dict[str, str] = {}

    forced_groups: list[str] = []
    unforced_groups: list[str] = []
    forced_destinations: dict[str, str] = {}
    for group, rows_in_group in groups.items():
        forced = {str(row["forced_split"]) for row in rows_in_group if row.get("forced_split")}
        if len(forced) > 1 or (forced and next(iter(forced)) not in SPLITS):
            raise ValueError(f"group {group!r} has conflicting or invalid forced_split")
        if forced:
            forced_groups.append(group)
            forced_destinations[group] = next(iter(forced))
        else:
            unforced_groups.append(group)
    sort_key = lambda group: (
        -len(groups[group]),
        _hmac_hex(salt, "diagnostic-group-order", group),
    )
    forced_groups.sort(key=sort_key)
    unforced_groups.sort(key=sort_key)

    def objective(
        candidate_total: Counter[str],
        candidate_cells: dict[str, dict[str, Counter[str]]],
    ) -> float:
        value = 0.0
        for split_name in SPLITS:
            target = total_targets[split_name]
            delta = (candidate_total[split_name] - target) / max(1, target)
            value += weights["total_count"] * delta * delta
            overshoot = max(0, candidate_total[split_name] - target) / max(1, target)
            value += 1000.0 * overshoot * overshoot
        for dimension in DIMENSIONS:
            weight = weights[dimension]
            for cell, targets in cell_targets[dimension].items():
                for split_name in SPLITS:
                    target = targets[split_name]
                    delta = (candidate_cells[dimension][split_name][cell] - target) / max(1, target)
                    value += weight * delta * delta
        return value

    def apply_group(group: str, selected: str) -> None:
        rows_in_group = groups[group]
        group_assignment[group] = selected
        counts_total[selected] += len(rows_in_group)
        for row in rows_in_group:
            for dimension in DIMENSIONS:
                counts_cells[dimension][selected][_normalise_cell(row[dimension])] += 1

    if exact_targets_by_stratum is not None:
        group_strata: dict[str, str] = {}
        for group, rows_in_group in groups.items():
            strata = {str(row["selection_stratum"]) for row in rows_in_group}
            if len(strata) != 1:
                raise ValueError(f"group {group!r} crosses exact split strata")
            group_strata[group] = next(iter(strata))
        observed_strata = set(group_strata.values())
        if observed_strata != set(exact_targets_by_stratum):
            raise ValueError(
                "exact target strata differ from input: "
                f"missing={sorted(observed_strata - set(exact_targets_by_stratum))}, "
                f"extra={sorted(set(exact_targets_by_stratum) - observed_strata)}"
            )

        for stratum in sorted(observed_strata):
            target = exact_targets_by_stratum[stratum]
            if set(target) != {"total", *SPLITS}:
                raise ValueError(f"exact target {stratum!r} must define total and all splits")
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in target.values()
            ):
                raise ValueError(f"exact target {stratum!r} contains an invalid count")
            if target["total"] != sum(target[name] for name in SPLITS):
                raise ValueError(f"exact target {stratum!r} does not sum to total")

            stratum_groups = sorted(
                (group for group, value in group_strata.items() if value == stratum),
                key=lambda group: (_hmac_hex(salt, "exact-order", stratum, group), group),
            )
            if sum(len(groups[group]) for group in stratum_groups) != target["total"]:
                raise ValueError(f"exact target {stratum!r} total differs from selected lineages")

            development_target = target["development"]
            calibration_target = target["calibration"]

            # suffix[index][d] is a bitset of calibration counts reachable by
            # assigning groups[index:].  It is an exact feasibility oracle;
            # balance scoring is permitted to choose only a transition that
            # keeps the frozen quotas reachable.
            initial = [0] * (development_target + 1)
            initial[0] = 1
            suffix: list[tuple[int, ...]] = [()] * (len(stratum_groups) + 1)
            suffix[-1] = tuple(initial)
            calibration_mask = (1 << (calibration_target + 1)) - 1
            for index in range(len(stratum_groups) - 1, -1, -1):
                group = stratum_groups[index]
                weight = len(groups[group])
                allowed = (
                    (forced_destinations[group],)
                    if group in forced_destinations
                    else SPLITS
                )
                following = suffix[index + 1]
                reachable = [0] * (development_target + 1)
                for following_development, calibration_bits in enumerate(following):
                    if not calibration_bits:
                        continue
                    for split_name in allowed:
                        development_count = following_development
                        bits = calibration_bits
                        if split_name == "development":
                            development_count += weight
                            if development_count > development_target:
                                continue
                        elif split_name == "calibration":
                            bits = (bits << weight) & calibration_mask
                        reachable[development_count] |= bits
                suffix[index] = tuple(reachable)

            if not (suffix[0][development_target] & (1 << calibration_target)):
                raise ValueError(f"exact grouped split is infeasible for stratum {stratum!r}")

            stratum_rows = [row for group in stratum_groups for row in groups[group]]
            balance_dimensions = tuple(
                dimension for dimension in DIMENSIONS if dimension != "selection_stratum"
            )
            final_targets = {
                dimension: _forced_aware_targets(
                    stratum_rows,
                    dimension=dimension,
                    ratios=ratios,
                    honor_forced=dimension == "category",
                )
                for dimension in balance_dimensions
            }
            prefix_totals: dict[str, Counter[str]] = {
                dimension: Counter() for dimension in balance_dimensions
            }
            prefix_by_split: dict[str, dict[str, Counter[str]]] = {
                dimension: {name: Counter() for name in SPLITS}
                for dimension in balance_dimensions
            }

            assigned_development = 0
            assigned_calibration = 0
            reconstructed: dict[str, str] = {}
            for index, group in enumerate(stratum_groups):
                weight = len(groups[group])
                allowed = (
                    (forced_destinations[group],)
                    if group in forced_destinations
                    else SPLITS
                )
                candidates: list[tuple[float, str, str]] = []
                for split_name in allowed:
                    next_development = assigned_development + (
                        weight if split_name == "development" else 0
                    )
                    next_calibration = assigned_calibration + (
                        weight if split_name == "calibration" else 0
                    )
                    remaining_development = development_target - next_development
                    remaining_calibration = calibration_target - next_calibration
                    if (
                        remaining_development < 0
                        or remaining_calibration < 0
                        or not (
                            suffix[index + 1][remaining_development]
                            & (1 << remaining_calibration)
                        )
                    ):
                        continue

                    # Compare the processed prefix to a forced-aware, rounded
                    # version of each final cell target.  This gives secondary
                    # stratification a deterministic role while exact quotas
                    # remain hard constraints.
                    score = 0.0
                    group_rows = groups[group]
                    for dimension in balance_dimensions:
                        added_cells = Counter(
                            _normalise_cell(row[dimension]) for row in group_rows
                        )
                        cells = set(prefix_totals[dimension]) | set(added_cells)
                        for cell in cells:
                            processed = prefix_totals[dimension][cell] + added_cells[cell]
                            final = final_targets[dimension][cell]
                            cell_total = sum(final.values())
                            shares = {
                                name: final[name] / cell_total for name in SPLITS
                            }
                            desired = _largest_remainder(processed, shares)
                            for name in SPLITS:
                                observed = prefix_by_split[dimension][name][cell]
                                if name == split_name:
                                    observed += added_cells[cell]
                                delta = observed - desired[name]
                                score += weights[dimension] * delta * delta / max(
                                    1, desired[name]
                                )
                    candidates.append(
                        (
                            score,
                            _hmac_hex(salt, "exact-choice", group, split_name),
                            split_name,
                        )
                    )
                if not candidates:  # pragma: no cover - guarded by suffix oracle
                    raise AssertionError("no exact, feasible split transition")
                _, _, selected = min(candidates)
                reconstructed[group] = selected
                if selected == "development":
                    assigned_development += weight
                elif selected == "calibration":
                    assigned_calibration += weight
                for row in groups[group]:
                    for dimension in balance_dimensions:
                        cell = _normalise_cell(row[dimension])
                        prefix_totals[dimension][cell] += 1
                        prefix_by_split[dimension][selected][cell] += 1

            if (
                assigned_development != development_target
                or assigned_calibration != calibration_target
            ):  # pragma: no cover
                raise AssertionError("exact grouped split did not reach its target")
            for group in stratum_groups:
                apply_group(group, reconstructed[group])
            realised = Counter(
                {
                    name: sum(
                        len(groups[group])
                        for group in stratum_groups
                        if reconstructed[group] == name
                    )
                    for name in SPLITS
                }
            )
            if any(realised[name] != target[name] for name in SPLITS):  # pragma: no cover
                raise AssertionError(f"exact target mismatch for {stratum!r}: {realised!r}")
    else:
        # OOD and other pre-registered reservations affect the objective seen by
        # every unforced group, so they must be applied before greedy scoring.
        for group in forced_groups:
            apply_group(group, forced_destinations[group])

        for group in unforced_groups:
            rows_in_group = groups[group]
            scored: list[tuple[float, str, str]] = []
            for split_name in SPLITS:
                trial_total = copy.copy(counts_total)
                trial_cells = {
                    dimension: {name: copy.copy(counter) for name, counter in by_split.items()}
                    for dimension, by_split in counts_cells.items()
                }
                trial_total[split_name] += len(rows_in_group)
                for row in rows_in_group:
                    for dimension in DIMENSIONS:
                        trial_cells[dimension][split_name][_normalise_cell(row[dimension])] += 1
                scored.append(
                    (
                        objective(trial_total, trial_cells),
                        _hmac_hex(salt, "diagnostic-choice", group, split_name),
                        split_name,
                    )
                )
            _, _, selected = min(scored)
            apply_group(group, selected)

    assignments = {
        lineage: group_assignment[group] for lineage, group in sorted(seen_lineages.items())
    }
    for identity_field in ("source_uid", "creator_group"):
        identity_splits: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            identity = str(row[identity_field])
            if not identity:
                raise ValueError(f"{identity_field} must be non-empty")
            identity_splits[identity].add(assignments[str(row["lineage_id"])])
        leaked = sorted(
            identity for identity, destinations in identity_splits.items() if len(destinations) > 1
        )
        if leaked:
            raise ValueError(
                f"{identity_field} values cross split boundaries; leakage groups are incomplete: {leaked[:5]}"
            )
    return assignments


def build_split_manifest(
    records: Iterable[dict[str, Any]],
    *,
    salt_hex: str,
    protocol_root_sha256: str,
    exact_targets_by_stratum: Mapping[str, Mapping[str, int]] | None = None,
) -> dict[str, Any]:
    """Return a schema-conformant split manifest, not a lossy dict."""

    rows = [dict(record) for record in records]
    assignments = assign_grouped_split(
        rows,
        salt_hex=salt_hex,
        exact_targets_by_stratum=exact_targets_by_stratum,
    )
    by_lineage = {str(row["lineage_id"]): row for row in rows}
    assignment_rows = []
    counts = Counter()
    for lineage, split_name in sorted(assignments.items()):
        row = by_lineage[lineage]
        if split_name != "blind":
            blind_scope = "NONE"
        elif row.get("blind_scope") == "OOD":
            if row["selection_stratum"] != "objaverse" or row.get("forced_split") != "blind":
                raise ValueError("OOD blind scope is reserved to forced Objaverse holdout rows")
            blind_scope = "OOD"
        elif row["selection_stratum"] == "objaverse":
            blind_scope = "IID"
        else:
            blind_scope = "TRANSFER"
        assignment_rows.append(
            {
                "lineage_id": lineage,
                "leakage_group_id": str(row["leakage_group_id"]),
                "split": split_name,
                "selection_stratum": str(row["selection_stratum"]),
                "blind_scope": blind_scope,
                "creator_group": str(row["creator_group"]),
                "source_uid": str(row["source_uid"]),
            }
        )
        counts[split_name] += 1
    ratios = {"development": 0.5, "calibration": 0.2, "blind": 0.3}
    total_targets = _largest_remainder(len(rows), ratios)
    deviations: list[dict[str, Any]] = []
    for name in SPLITS:
        difference = counts[name] - total_targets[name]
        if difference:
            deviations.append(
                {
                    "dimension": "total_count",
                    "cell": "<ALL>",
                    "split": name,
                    "target": total_targets[name],
                    "observed": counts[name],
                    "observed_minus_target": difference,
                    "allowed_absolute_deviation": 0,
                    "within_bound": False,
                }
            )

    rows_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        rows_by_group[str(row["leakage_group_id"])].append(row)
    for dimension in DIMENSIONS:
        if dimension == "selection_stratum" and exact_targets_by_stratum is not None:
            targets_by_cell = {
                stratum: {name: int(target[name]) for name in SPLITS}
                for stratum, target in exact_targets_by_stratum.items()
            }
        else:
            targets_by_cell = _forced_aware_targets(
                rows,
                dimension=dimension,
                ratios=ratios,
                honor_forced=dimension == "category",
            )
        observed_by_cell: dict[str, Counter[str]] = defaultdict(Counter)
        for row in rows:
            cell = _normalise_cell(row[dimension])
            observed_by_cell[cell][assignments[str(row["lineage_id"])]] += 1
        largest_group_by_cell: Counter[str] = Counter()
        for group_rows in rows_by_group.values():
            contribution = Counter(_normalise_cell(row[dimension]) for row in group_rows)
            for cell, count in contribution.items():
                largest_group_by_cell[cell] = max(largest_group_by_cell[cell], count)
        for cell, target in sorted(targets_by_cell.items()):
            for name in SPLITS:
                observed = observed_by_cell[cell][name]
                difference = observed - target[name]
                if not difference:
                    continue
                limit = _secondary_balance_limit(
                    dimension=dimension,
                    target=target[name],
                    largest_group=largest_group_by_cell[cell],
                )
                deviations.append(
                    {
                        "dimension": dimension,
                        "cell": cell,
                        "split": name,
                        "target": target[name],
                        "observed": observed,
                        "observed_minus_target": difference,
                        "allowed_absolute_deviation": limit,
                        "within_bound": abs(difference) <= limit,
                    }
                )
    if exact_targets_by_stratum is not None:
        violations = [item for item in deviations if not item["within_bound"]]
        if violations:
            first = violations[0]
            raise ValueError(
                "secondary split imbalance exceeds frozen bound: "
                f"{first['dimension']}={first['cell']} {first['split']} "
                f"delta={first['observed_minus_target']} "
                f"limit={first['allowed_absolute_deviation']}"
            )

    canonical_rows = canonical_json_bytes(
        sorted(
            (_commitment_row(row) for row in rows),
            key=lambda row: str(row["lineage_id"]),
        ),
    )
    return {
        "schema_version": "0.1.0",
        "algorithm_id": ALGORITHM_ID,
        "algorithm_version": ALGORITHM_VERSION,
        "implementation_sha256": _implementation_sha256(),
        "protocol_root_sha256": protocol_root_sha256,
        "salt_sha256": hashlib.sha256(bytes.fromhex(salt_hex)).hexdigest(),
        "input_records_sha256": hashlib.sha256(canonical_rows).hexdigest(),
        "assignments": assignment_rows,
        "counts": {**{name: counts[name] for name in SPLITS}, "reserve": 0},
        "deviations": deviations,
    }
