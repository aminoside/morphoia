"""Outcome-independent cohort selection for the MVX feasibility protocol."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from .hmac_rank import hmac_sha256_rank

ALGORITHM_ID = "MVX-COHORT-HMAC-2"
ALGORITHM_VERSION = "2.0.0"
VISIBLE_MILESTONE_ALGORITHM_ID = "MVX-VISIBLE-MILESTONES-HMAC-2"
VISIBLE_MILESTONE_ALGORITHM_VERSION = "2.0.0"
COMPLEXITY_TIEBREAK_ALGORITHM_ID = "MVX-COMPLEXITY-TIEBREAK-HMAC-1"
COMPLEXITY_TIEBREAK_ALGORITHM_VERSION = "1.0.0"
COMPLEXITY_BOOTSTRAP_SEED_HEX = "713b129c8347d84b37685cca9ef0734e6599ca90691b852eacb561f4bef148f0"
DEFAULT_TARGETS = {
    "fixtures_C0_C9": 100,
    "objaverse": 600,
    "modelnet40": 100,
    "thingi10k": 80,
    "google_scanned_objects": 60,
    "human_anatomy": 50,
    "plants": 10,
}
DEFAULT_VISIBLE_MILESTONES = {
    "n12": {
        "fixtures_C0_C9": 8,
        "objaverse": 2,
        "google_scanned_objects": 1,
        "human_anatomy": 1,
    },
    "n30": {
        "fixtures_C0_C9": 15,
        "objaverse": 8,
        "modelnet40": 2,
        "google_scanned_objects": 3,
        "human_anatomy": 2,
    },
    "n100": {
        "fixtures_C0_C9": 60,
        "objaverse": 16,
        "modelnet40": 6,
        "thingi10k": 6,
        "google_scanned_objects": 6,
        "human_anatomy": 6,
    },
    "n300": {
        "fixtures_C0_C9": 70,
        "objaverse": 125,
        "modelnet40": 30,
        "thingi10k": 25,
        "google_scanned_objects": 20,
        "human_anatomy": 25,
        "plants": 5,
    },
}


@dataclass(frozen=True)
class SelectionResult:
    """Complete selected/reserve decision without source paths."""

    selected_lineages: tuple[str, ...]
    reserve_lineages: tuple[str, ...]
    forced_split: Mapping[str, str]
    blind_scope: Mapping[str, str]
    selected_counts: Mapping[str, int]
    ood_categories: tuple[str, ...]


def _secret_bytes(seed_hex: str) -> bytes:
    try:
        value = bytes.fromhex(seed_hex)
    except ValueError as error:
        raise ValueError("selection_seed_hex must be hexadecimal") from error
    if len(value) != 32:
        raise ValueError("selection_seed_hex must encode exactly 256 bits")
    return value


def _rank(
    seed: bytes,
    domain: str,
    *parts: str,
    algorithm_id: str = ALGORITHM_ID,
    algorithm_version: str = ALGORITHM_VERSION,
) -> bytes:
    return hmac_sha256_rank(
        seed,
        algorithm_id=algorithm_id,
        algorithm_version=algorithm_version,
        domain=domain,
        parts=parts,
    )


def complexity_tie_rank(lineage_id: str) -> bytes:
    """Rank a P2a triangle-count tie without any production selection secret."""

    return hmac_sha256_rank(
        bytes.fromhex(COMPLEXITY_BOOTSTRAP_SEED_HEX),
        algorithm_id=COMPLEXITY_TIEBREAK_ALGORITHM_ID,
        algorithm_version=COMPLEXITY_TIEBREAK_ALGORITHM_VERSION,
        domain="complexity-quantile-tie",
        parts=(lineage_id,),
    )


def _exact_ranked_subset(
    candidates: list[tuple[str, int]],
    *,
    target: int,
    seed: bytes,
    domain: str,
    rank_prefix: tuple[str, ...] = (),
    algorithm_id: str = ALGORITHM_ID,
    algorithm_version: str = ALGORITHM_VERSION,
) -> tuple[str, ...]:
    """Choose a deterministic exact subset of weighted atomic candidates.

    Dynamic programming follows HMAC rank order and preserves the first
    reachable representation of every sum.  It never truncates an atomic
    leakage group or category.
    """

    if target < 0:
        raise ValueError("selection target must be non-negative")
    ordered = sorted(
        candidates,
        key=lambda item: (
            _rank(
                seed,
                domain,
                *rank_prefix,
                item[0],
                algorithm_id=algorithm_id,
                algorithm_version=algorithm_version,
            ),
            item[0],
        ),
    )
    reachable: dict[int, tuple[str, ...]] = {0: ()}
    for identifier, weight in ordered:
        if weight <= 0:
            raise ValueError(f"candidate {identifier!r} has non-positive weight")
        additions: dict[int, tuple[str, ...]] = {}
        for subtotal, chosen in list(reachable.items()):
            updated = subtotal + weight
            if updated <= target and updated not in reachable and updated not in additions:
                additions[updated] = (*chosen, identifier)
        reachable.update(additions)
    if target not in reachable:
        available = sum(weight for _, weight in candidates)
        raise ValueError(
            f"cannot satisfy exact target {target} in {domain!r}; available={available}"
        )
    return reachable[target]


def select_cohort(
    records: Iterable[dict[str, Any]],
    *,
    selection_seed_hex: str,
    targets: Mapping[str, int] | None = None,
    objaverse_ood_target: int = 60,
) -> SelectionResult:
    """Select the frozen cohort and reserve without consulting MVX outcomes."""

    seed = _secret_bytes(selection_seed_hex)
    requested = dict(DEFAULT_TARGETS if targets is None else targets)
    if set(requested) != set(DEFAULT_TARGETS):
        raise ValueError(f"targets must define exactly {sorted(DEFAULT_TARGETS)}")
    if any(
        isinstance(value, bool) or not isinstance(value, int) or value < 0
        for value in requested.values()
    ):
        raise ValueError("all targets must be non-negative integers")
    if objaverse_ood_target < 0 or objaverse_ood_target > requested["objaverse"]:
        raise ValueError("Objaverse OOD target must lie inside the Objaverse target")

    required = {
        "lineage_id",
        "leakage_group_id",
        "selection_stratum",
        "category",
        "creator_group",
        "source_uid",
        "eligibility",
    }
    rows = [dict(record) for record in records]
    seen_lineages: set[str] = set()
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        missing = required - set(row)
        if missing:
            raise ValueError(f"selection record missing fields: {sorted(missing)}")
        lineage = str(row["lineage_id"])
        group = str(row["leakage_group_id"])
        if not lineage or not group:
            raise ValueError("lineage_id and leakage_group_id must be non-empty")
        if lineage in seen_lineages:
            raise ValueError(f"lineage {lineage!r} occurs more than once")
        seen_lineages.add(lineage)
        if row["eligibility"] == "ELIGIBLE":
            groups[group].append(row)
        elif row["eligibility"] not in {"EXCLUDED", "PENDING"}:
            raise ValueError(f"invalid eligibility for lineage {lineage!r}")

    group_stratum: dict[str, str] = {}
    group_category: dict[str, str] = {}
    for group, members in groups.items():
        strata = {str(member["selection_stratum"]) for member in members}
        if len(strata) != 1 or next(iter(strata)) not in requested:
            raise ValueError(f"group {group!r} must have one registered selection_stratum")
        group_stratum[group] = next(iter(strata))
        categories = {str(member["category"]) for member in members}
        if group_stratum[group] == "objaverse" and (
            len(categories) != 1 or not next(iter(categories))
        ):
            raise ValueError(f"Objaverse group {group!r} must have one non-empty category")
        group_category[group] = next(iter(categories)) if len(categories) == 1 else "<MIXED>"

    for identity_field in ("source_uid", "creator_group"):
        identity_groups: dict[str, set[str]] = defaultdict(set)
        for group, members in groups.items():
            for member in members:
                identity = str(member[identity_field])
                if not identity:
                    raise ValueError(f"{identity_field} must be non-empty")
                identity_groups[identity].add(group)
        incomplete = sorted(
            identity
            for identity, member_groups in identity_groups.items()
            if len(member_groups) > 1
        )
        if incomplete:
            raise ValueError(
                f"{identity_field} values span multiple leakage groups: {incomplete[:5]}"
            )

    selected_groups: set[str] = set()
    forced_split: dict[str, str] = {}
    blind_scope: dict[str, str] = {}

    objaverse_categories: dict[str, list[str]] = defaultdict(list)
    for group, stratum in group_stratum.items():
        if stratum == "objaverse":
            objaverse_categories[group_category[group]].append(group)
    category_candidates = [
        (category, sum(len(groups[group]) for group in category_groups))
        for category, category_groups in objaverse_categories.items()
    ]
    ood_categories = _exact_ranked_subset(
        category_candidates,
        target=objaverse_ood_target,
        seed=seed,
        domain="objaverse-ood-category",
    )
    for category in ood_categories:
        for group in objaverse_categories[category]:
            selected_groups.add(group)
            for member in groups[group]:
                lineage = str(member["lineage_id"])
                forced_split[lineage] = "blind"
                blind_scope[lineage] = "OOD"

    for stratum, target in requested.items():
        already = sum(
            len(groups[group]) for group in selected_groups if group_stratum[group] == stratum
        )
        remaining = target - already
        if remaining < 0:
            raise ValueError(f"pre-reserved OOD groups exceed {stratum!r} target")
        candidates = [
            (group, len(groups[group]))
            for group in groups
            if group_stratum[group] == stratum and group not in selected_groups
        ]
        chosen = _exact_ranked_subset(
            candidates,
            target=remaining,
            seed=seed,
            domain="cohort-stratum",
            rank_prefix=(stratum,),
        )
        selected_groups.update(chosen)

    selected: list[str] = []
    reserve: list[str] = []
    selected_counts: Counter[str] = Counter()
    for group in sorted(groups):
        destination = selected if group in selected_groups else reserve
        for member in sorted(groups[group], key=lambda item: str(item["lineage_id"])):
            lineage = str(member["lineage_id"])
            destination.append(lineage)
            if group in selected_groups:
                selected_counts[group_stratum[group]] += 1
                blind_scope.setdefault(lineage, "NONE")

    if dict(selected_counts) != requested:
        raise AssertionError(f"internal selection-count mismatch: {selected_counts!r}")
    return SelectionResult(
        selected_lineages=tuple(sorted(selected)),
        reserve_lineages=tuple(sorted(reserve)),
        forced_split=dict(sorted(forced_split.items())),
        blind_scope=dict(sorted(blind_scope.items())),
        selected_counts=dict(sorted(selected_counts.items())),
        ood_categories=tuple(ood_categories),
    )


def select_visible_milestones(
    records: Iterable[dict[str, Any]],
    *,
    selection_seed_hex: str,
    compositions: Mapping[str, Mapping[str, int]] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Select exact nested n12/n30/n100/n300 sets from visible records only."""

    seed = _secret_bytes(selection_seed_hex)
    requested = dict(DEFAULT_VISIBLE_MILESTONES if compositions is None else compositions)
    if tuple(requested) != ("n12", "n30", "n100", "n300"):
        raise ValueError("visible milestones must be ordered n12, n30, n100, n300")

    rows = [dict(record) for record in records]
    required = {"lineage_id", "leakage_group_id", "selection_stratum", "split"}
    seen_lineages: set[str] = set()
    visible_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    group_splits: dict[str, set[str]] = defaultdict(set)
    group_strata: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        missing = required - set(row)
        if missing:
            raise ValueError(f"milestone record missing fields: {sorted(missing)}")
        lineage = str(row["lineage_id"])
        group = str(row["leakage_group_id"])
        if lineage in seen_lineages:
            raise ValueError(f"lineage {lineage!r} occurs more than once")
        seen_lineages.add(lineage)
        split = str(row["split"])
        if split not in {"development", "calibration", "blind", "reserve"}:
            raise ValueError(f"invalid split {split!r}")
        group_splits[group].add(split)
        group_strata[group].add(str(row["selection_stratum"]))
        if split in {"development", "calibration"}:
            visible_groups[group].append(row)
    if any(len(splits) != 1 for splits in group_splits.values()):
        raise ValueError("a leakage group crosses split boundaries")
    if any(len(strata) != 1 for strata in group_strata.values()):
        raise ValueError("a leakage group crosses selection strata")

    selected_groups: set[str] = set()
    result: dict[str, tuple[str, ...]] = {}
    prior_targets: Counter[str] = Counter()
    for milestone, target_mapping in requested.items():
        targets = Counter(target_mapping)
        if any(
            isinstance(value, bool) or not isinstance(value, int) or value < 0
            for value in targets.values()
        ):
            raise ValueError(f"milestone {milestone!r} has an invalid target")
        for stratum, previous in prior_targets.items():
            if targets[stratum] < previous:
                raise ValueError(f"milestone {milestone!r} decreases stratum {stratum!r}")
        for stratum, target in sorted(targets.items()):
            already = sum(
                len(visible_groups[group])
                for group in selected_groups
                if next(iter(group_strata[group])) == stratum
            )
            need = target - already
            candidates = [
                (group, len(members))
                for group, members in visible_groups.items()
                if group not in selected_groups and next(iter(group_strata[group])) == stratum
            ]
            chosen = _exact_ranked_subset(
                candidates,
                target=need,
                seed=seed,
                domain="visible-milestone-stratum",
                rank_prefix=(stratum,),
                algorithm_id=VISIBLE_MILESTONE_ALGORITHM_ID,
                algorithm_version=VISIBLE_MILESTONE_ALGORITHM_VERSION,
            )
            selected_groups.update(chosen)

        selected_lineages = tuple(
            sorted(
                str(row["lineage_id"]) for group in selected_groups for row in visible_groups[group]
            )
        )
        expected_size = int(milestone[1:])
        if len(selected_lineages) != expected_size:
            raise ValueError(
                f"milestone {milestone!r} selected {len(selected_lineages)}, "
                f"expected {expected_size}"
            )
        result[milestone] = selected_lineages
        prior_targets = targets
    return result
