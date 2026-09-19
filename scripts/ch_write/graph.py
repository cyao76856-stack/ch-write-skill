"""Dependency graph traversal and impact analysis for CH-Write projects.

The current object state lives in ``indexes/entities.json`` and the current
effective relations live in ``indexes/relations.json``.  If the relation index
is missing, the effective state is rebuilt read-only from the append-only
relation log.
"""
from __future__ import annotations

import re
from collections import deque
from pathlib import Path

from .io import read_json
from .objects import effective_relations

_OBJECT_ID_PATTERN = re.compile(r"^([A-Z]{3})-([0-9]{4,})$")
_RELATION_INDEX = "indexes/relations.json"


def _load_entities(root: Path) -> dict:
    path = Path(root) / "indexes" / "entities.json"
    if not path.exists():
        return {}
    data = read_json(path)
    objects = data.get("objects")
    if not isinstance(objects, dict):
        raise ValueError("invalid entities index")
    return objects


def _load_active_relations(root: Path) -> list[dict]:
    path = Path(root) / _RELATION_INDEX
    if path.exists():
        data = read_json(path)
        relations = data.get("relations")
        if not isinstance(relations, list):
            raise ValueError("invalid relations index")
        return [
            relation for relation in relations
            if isinstance(relation, dict) and relation.get("status") == "active"
        ]

    return [
        relation for relation in effective_relations(root)
        if isinstance(relation, dict) and relation.get("status") == "active"
    ]


def impact(root: Path, object_id: str) -> dict:
    """Return the downstream impact report for ``object_id``.

    Traversal is breadth-first and follows active outbound relations only.
    Direct objects are one relation hop away; indirect objects are every
    object reachable at depth two or greater.
    """
    root = Path(root)
    if not isinstance(object_id, str) or _OBJECT_ID_PATTERN.fullmatch(object_id) is None:
        raise ValueError(f"invalid object_id: {object_id}")

    entities = _load_entities(root)
    entry = entities.get(object_id)
    if not isinstance(entry, dict):
        raise ValueError(f"unknown object_id: {object_id}")

    adjacency: dict[str, list[str]] = {}
    for relation in _load_active_relations(root):
        source = relation.get("source_id")
        target = relation.get("target_id")
        if isinstance(source, str) and isinstance(target, str):
            adjacency.setdefault(source, []).append(target)

    depths = {object_id: 0}
    queue = deque([object_id])
    while queue:
        current = queue.popleft()
        for neighbor in adjacency.get(current, []):
            if neighbor not in depths:
                depths[neighbor] = depths[current] + 1
                queue.append(neighbor)

    direct = sorted(object_id for object_id, depth in depths.items() if depth == 1)
    indirect = sorted(object_id for object_id, depth in depths.items() if depth >= 2)
    reachable = set(direct) | set(indirect)

    by_category: dict[str, list[str]] = {}
    for impacted_id in direct + indirect:
        impacted_entry = entities.get(impacted_id)
        category = impacted_entry.get("type") if isinstance(impacted_entry, dict) else "unknown"
        by_category.setdefault(category, []).append(impacted_id)
    for category in by_category:
        by_category[category] = sorted(set(by_category[category]))

    review_only = sorted(
        source
        for source, targets in adjacency.items()
        if source != object_id and source not in reachable
        and (object_id in targets or any(target in reachable for target in targets))
    )

    return {
        "object_id": object_id,
        "direct": direct,
        "indirect": indirect,
        "by_category": by_category,
        "classification": {
            "must_change": direct,
            "may_change": indirect,
            "review_only": review_only,
        },
    }
