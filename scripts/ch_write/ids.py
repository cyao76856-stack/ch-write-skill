import re
from pathlib import Path

from .constants import ID_PREFIXES
from .io import read_json, read_jsonl

_OBJECT_ID_PATTERN = re.compile(r"^([A-Z]{3})-([0-9]+)$")


def _collect_numbers(prefix, records, key):
    numbers = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        value = record.get(key)
        if not isinstance(value, str):
            continue
        match = _OBJECT_ID_PATTERN.fullmatch(value)
        if match is None or match.group(1) != prefix:
            continue
        numbers.add(int(match.group(2)))
    return numbers


def allocate_id(root: Path, object_type: str) -> str:
    """Return the next permanent ID for ``object_type``.

    IDs are allocated by scanning the entities index, the per-type object log,
    and, for relations, the relation log and relation index. Numbers are never
    reused because every source is scanned and the maximum is incremented.
    """
    root = Path(root)
    if object_type not in ID_PREFIXES:
        raise ValueError(f"unknown object type: {object_type}")
    prefix = ID_PREFIXES[object_type]

    numbers = set()

    entities_path = root / "indexes" / "entities.json"
    if entities_path.exists():
        data = read_json(entities_path)
        objects = data.get("objects", {})
        if isinstance(objects, dict):
            numbers.update(_collect_numbers(prefix, [{"object_id": key} for key in objects], "object_id"))
            for entry in objects.values():
                if isinstance(entry, dict):
                    numbers.update(_collect_numbers(prefix, [entry], "object_id"))

    object_log = root / "store" / "objects" / f"{object_type}.jsonl"
    numbers.update(
        _collect_numbers(prefix, read_jsonl(object_log), "object_id")
    )

    if object_type == "relation":
        numbers.update(
            _collect_numbers(
                prefix, read_jsonl(root / "store" / "relations.jsonl"), "relation_id"
            )
        )
        relations_index = root / "indexes" / "relations.json"
        if relations_index.exists():
            data = read_json(relations_index)
            relations = data.get("relations", [])
            if isinstance(relations, list):
                numbers.update(_collect_numbers(prefix, relations, "relation_id"))

    next_number = max(numbers, default=0) + 1
    return f"{prefix}-{next_number:04d}"