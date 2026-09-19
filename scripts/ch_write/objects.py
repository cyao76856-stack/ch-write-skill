import copy
import re
from datetime import datetime, timezone
from pathlib import Path

from .constants import CANON_MEMBERSHIP_VALUES, ID_PREFIXES, NARRATIVE_OBJECT_TYPES, PROVENANCE_VALUES
from .ids import allocate_id
from .io import append_jsonl, read_json, read_jsonl, write_json_atomic

RELATION_VALUES = (
    "depends_on", "causes", "blocks", "enables", "contains", "appears_in",
    "knows", "owns", "affects", "contradicts", "supersedes", "same_as",
    "derived_from",
)

_OBJECT_ID_PATTERN = re.compile(r"^[A-Z]{3}-[0-9]{4,}$")
_REVISION_PATTERN = re.compile(r"^rev-([0-9]+)$")
_SOURCE_REF_PATTERN = re.compile(r"^SRC-[0-9]{4,}$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entities_path(root: Path) -> Path:
    return Path(root) / "indexes" / "entities.json"


def _object_log_path(root: Path, object_type: str) -> Path:
    return Path(root) / "store" / "objects" / f"{object_type}.jsonl"


def _relations_log_path(root: Path) -> Path:
    return Path(root) / "store" / "relations.jsonl"


def _relations_index_path(root: Path) -> Path:
    return Path(root) / "indexes" / "relations.json"


def _validate_object_type(object_type: str) -> None:
    if object_type not in NARRATIVE_OBJECT_TYPES:
        raise ValueError(f"unsupported narrative object type: {object_type}")


def _validate_object_id(object_id: str) -> None:
    if not isinstance(object_id, str) or _OBJECT_ID_PATTERN.fullmatch(object_id) is None:
        raise ValueError(f"invalid object_id: {object_id}")


def _validate_name(name: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise ValueError("name must be a non-empty string")
    return name


def _validate_mapping(value: dict, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a dict")
    return copy.deepcopy(value)


def _validate_reason(reason: str) -> str:
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason must be a non-empty string")
    return reason


def _next_revision(revision: str | None) -> str:
    match = _REVISION_PATTERN.fullmatch(revision or "")
    number = int(match.group(1)) if match else 0
    return f"rev-{number + 1:04d}"


def _load_entities(root: Path) -> dict:
    path = _entities_path(root)
    if not path.exists():
        return {}
    data = read_json(path)
    objects = data.get("objects", {})
    if not isinstance(objects, dict):
        raise ValueError("invalid entities index")
    return objects


def _write_entities(root: Path, objects: dict) -> None:
    write_json_atomic(_entities_path(root), {"objects": objects})


def _entry_from_record(
    record: dict,
    history: list[str],
    tombstoned: bool,
    merged_into: str | None,
    merged_from: list[str],
) -> dict:
    entry = {
        "object_id": record["object_id"],
        "type": record["type"],
        "name": record["name"],
        "aliases": copy.deepcopy(record.get("aliases", [])),
        "attributes": copy.deepcopy(record.get("attributes", {})),
        "status": record.get("status", "active"),
        "revision": record["revision"],
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
        "history_revisions": list(history),
        "tombstoned": bool(tombstoned),
        "merged_into": merged_into,
        "merged_from": list(merged_from or []),
        "provenance": record.get("provenance", "proposed"),
        "source_refs": copy.deepcopy(record.get("source_refs", [])),
        "canon_membership": record.get("canon_membership", "excluded"),
    }
    for extra in ("tombstone_reason", "merge_reason", "merged_into", "canon_version"):
        if extra in record and record[extra] is not None:
            entry[extra] = record[extra]
    return entry


def _record_from_entry(entry: dict) -> dict:
    record = {
        "object_id": entry["object_id"],
        "type": entry["type"],
        "name": entry["name"],
        "aliases": copy.deepcopy(entry.get("aliases", [])),
        "attributes": copy.deepcopy(entry.get("attributes", {})),
        "status": entry.get("status", "active"),
        "revision": entry.get("revision"),
        "created_at": entry.get("created_at"),
        "updated_at": entry.get("updated_at"),
        "provenance": entry.get("provenance", "proposed"),
        "source_refs": copy.deepcopy(entry.get("source_refs", [])),
        "canon_membership": entry.get("canon_membership", "excluded"),
    }
    for extra in ("tombstone_reason", "merge_reason", "canon_version"):
        if extra in entry:
            record[extra] = entry[extra]
    return record


def _load_current(root: Path, object_id: str) -> tuple[dict, dict]:
    _validate_object_id(object_id)
    objects = _load_entities(root)
    entry = objects.get(object_id)
    if not isinstance(entry, dict):
        raise ValueError(f"unknown object_id: {object_id}")
    return _record_from_entry(entry), entry


def _is_active_endpoint(root: Path, object_id: str) -> None:
    _validate_object_id(object_id)
    entry = _load_entities(root).get(object_id)
    if not isinstance(entry, dict):
        raise ValueError(f"unknown object_id: {object_id}")
    if entry.get("tombstoned") or entry.get("merged_into") is not None:
        raise ValueError(f"object is not active: {object_id}")
    if entry.get("status") in ("tombstoned", "merged"):
        raise ValueError(f"object is not active: {object_id}")


def _history_with_new_revision(entry: dict, revision: str) -> list[str]:
    history = list(entry.get("history_revisions", []))
    if revision not in history:
        history.append(revision)
    return history


def _publish(
    root: Path,
    record: dict,
    history: list[str],
    tombstoned: bool = False,
    merged_into: str | None = None,
    merged_from: list[str] | None = None,
) -> dict:
    _validate_object_type(record["type"])
    append_jsonl(_object_log_path(root, record["type"]), record)

    objects = _load_entities(root)
    objects[record["object_id"]] = _entry_from_record(
        record, history, tombstoned, merged_into, merged_from or []
    )
    _write_entities(root, objects)

    return copy.deepcopy(record)


def add_object(
    root: Path,
    object_type: str,
    name: str,
    attributes: dict,
    provenance: str = "proposed",
    source_refs: list[str] | None = None,
    canon_membership: str = "excluded",
) -> dict:
    """Add a narrative object with explicit provenance and canon metadata."""
    root = Path(root)
    _validate_object_type(object_type)
    name = _validate_name(name)
    attributes = _validate_mapping(attributes, "attributes")

    if provenance not in PROVENANCE_VALUES:
        raise ValueError(f"provenance must be one of {PROVENANCE_VALUES}")
    if canon_membership not in CANON_MEMBERSHIP_VALUES:
        raise ValueError(f"canon_membership must be one of {CANON_MEMBERSHIP_VALUES}")
    if source_refs is None:
        source_refs = []
    if not isinstance(source_refs, list) or not all(isinstance(item, str) for item in source_refs):
        raise ValueError("source_refs must be a list of strings")
    for source_ref in source_refs:
        if _SOURCE_REF_PATTERN.fullmatch(source_ref) is None:
            raise ValueError(f"invalid source_ref: {source_ref}")

    object_id = allocate_id(root, object_type)
    now = _now()
    record = {
        "object_id": object_id,
        "type": object_type,
        "name": name,
        "aliases": [],
        "attributes": attributes,
        "status": "active",
        "provenance": provenance,
        "source_refs": copy.deepcopy(source_refs),
        "canon_membership": canon_membership,
        "revision": "rev-0001",
        "created_at": now,
        "updated_at": now,
    }
    return _publish(root, record, ["rev-0001"])


def update_object(root: Path, object_id: str, changes: dict) -> dict:
    root = Path(root)
    _validate_object_id(object_id)
    _is_active_endpoint(root, object_id)
    changes = _validate_mapping(changes, "changes")

    current, entry = _load_current(root, object_id)
    record = copy.deepcopy(current)
    if entry.get("canon_membership") == "active":
        record["canon_membership"] = "stale"
    record["attributes"] = copy.deepcopy(record.get("attributes", {}))
    record["attributes"].update(changes)
    record["revision"] = _next_revision(record.get("revision"))
    record["updated_at"] = _now()

    history = _history_with_new_revision(entry, record["revision"])
    return _publish(
        root,
        record,
        history,
        tombstoned=bool(entry.get("tombstoned", False)),
        merged_into=entry.get("merged_into"),
        merged_from=entry.get("merged_from", []),
    )


def rename_object(root: Path, object_id: str, new_name: str) -> dict:
    root = Path(root)
    _validate_object_id(object_id)
    _is_active_endpoint(root, object_id)
    new_name = _validate_name(new_name)

    current, entry = _load_current(root, object_id)
    record = copy.deepcopy(current)
    if entry.get("canon_membership") == "active":
        record["canon_membership"] = "stale"
    aliases = list(record.get("aliases", []))
    old_name = record.get("name")
    if new_name != old_name:
        if isinstance(old_name, str) and old_name and old_name not in aliases:
            aliases.append(old_name)
    record["name"] = new_name
    record["aliases"] = aliases
    record["revision"] = _next_revision(record.get("revision"))
    record["updated_at"] = _now()

    history = _history_with_new_revision(entry, record["revision"])
    return _publish(
        root,
        record,
        history,
        tombstoned=bool(entry.get("tombstoned", False)),
        merged_into=entry.get("merged_into"),
        merged_from=entry.get("merged_from", []),
    )


def tombstone_object(root: Path, object_id: str, reason: str) -> dict:
    root = Path(root)
    _validate_object_id(object_id)
    _is_active_endpoint(root, object_id)
    reason = _validate_reason(reason)

    current, entry = _load_current(root, object_id)
    record = copy.deepcopy(current)
    if entry.get("canon_membership") == "active":
        record["canon_membership"] = "stale"
    record["status"] = "tombstoned"
    record["tombstone_reason"] = reason
    record["revision"] = _next_revision(record.get("revision"))
    record["updated_at"] = _now()

    history = _history_with_new_revision(entry, record["revision"])
    return _publish(
        root,
        record,
        history,
        tombstoned=True,
        merged_into=entry.get("merged_into"),
        merged_from=entry.get("merged_from", []),
    )


def set_object_confirmed(root: Path, object_id: str, version: str) -> dict:
    """Mark an object as active canon in the entities index for ``version``."""
    root = Path(root)
    _validate_object_id(object_id)
    _is_active_endpoint(root, object_id)
    if not isinstance(version, str) or not version.strip():
        raise ValueError("version must be a non-empty string")

    objects = _load_entities(root)
    entry = objects.get(object_id)
    if not isinstance(entry, dict):
        raise ValueError(f"unknown object_id: {object_id}")
    entry["canon_membership"] = "active"
    entry["canon_version"] = version
    _write_entities(root, objects)
    return copy.deepcopy(entry)


def _read_relation_log(root: Path) -> list[dict]:
    return read_jsonl(_relations_log_path(root))


def _build_relation_chains(records: list[dict]) -> list[dict]:
    by_id = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        relation_id = record.get("relation_id")
        if isinstance(relation_id, str) and relation_id:
            by_id[relation_id] = copy.deepcopy(record)

    superseded_by = {}
    for record in records:
        if not isinstance(record, dict):
            continue
        supersedes = record.get("supersedes")
        relation_id = record.get("relation_id")
        if (
            isinstance(supersedes, str)
            and isinstance(relation_id, str)
            and supersedes in by_id
        ):
            superseded_by[supersedes] = relation_id

    roots = []
    for record in records:
        if not isinstance(record, dict):
            continue
        relation_id = record.get("relation_id")
        if not isinstance(relation_id, str) or not relation_id:
            continue
        supersedes = record.get("supersedes")
        if not isinstance(supersedes, str) or not supersedes:
            roots.append(record)

    chains = []
    for root in roots:
        chain_ids = []
        current_id = root.get("relation_id")
        seen = set()
        while isinstance(current_id, str) and current_id and current_id not in seen:
            seen.add(current_id)
            chain_ids.append(current_id)
            current_id = superseded_by.get(current_id)

        chain_records = [by_id[relation_id] for relation_id in chain_ids if relation_id in by_id]
        if not chain_records:
            continue

        terminal = chain_records[-1]
        history = []
        for old_record in chain_records[:-1]:
            old = copy.deepcopy(old_record)
            old["status"] = "superseded"
            history.append(old)

        head = copy.deepcopy(terminal)
        summary = {
            "relation_id": head.get("relation_id"),
            "source_id": head.get("source_id"),
            "relation": head.get("relation"),
            "target_id": head.get("target_id"),
            "evidence": copy.deepcopy(head.get("evidence")),
            "revision": head.get("revision"),
            "status": head.get("status", "active"),
            "supersedes": head.get("supersedes"),
            "created_at": head.get("created_at"),
            "history": history,
        }
        if head.get("reason"):
            summary["reason"] = head.get("reason")
        chains.append(summary)
    return chains

def _effective_relations(root: Path) -> list[dict]:
    return _build_relation_chains(_read_relation_log(root))


def effective_relations(root: Path) -> list[dict]:
    """Return the current effective relation chains for ``root``.

    The relation log is append-only; this helper rebuilds the current derived
    relation state without writing ``indexes/relations.json``.
    """
    return _effective_relations(root)


def _rebuild_relations_index(root: Path) -> None:
    write_json_atomic(
        _relations_index_path(root),
        {"relations": _effective_relations(root)},
    )


def _append_relation_record(root: Path, record: dict) -> dict:
    append_jsonl(_relations_log_path(root), record)
    _rebuild_relations_index(root)
    return copy.deepcopy(record)


def _replace_relation_endpoints_for_merge(
    root: Path,
    relation: dict,
    survivor_id: str,
    merged_id: str,
) -> None:
    source_id = relation.get("source_id")
    target_id = relation.get("target_id")
    if source_id == merged_id:
        source_id = survivor_id
    if target_id == merged_id:
        target_id = survivor_id

    relation_id = allocate_id(root, "relation")
    now = _now()
    replacement = {
        "relation_id": relation_id,
        "source_id": source_id,
        "relation": relation.get("relation"),
        "target_id": target_id,
        "evidence": copy.deepcopy(relation.get("evidence")),
        "revision": "rev-0001",
        "status": "active",
        "supersedes": relation.get("relation_id"),
        "created_at": now,
    }
    if source_id == target_id:
        replacement["status"] = "withdrawn"
        replacement["reason"] = "merge would create a self-reference"
    _append_relation_record(root, replacement)


def merge_objects(root: Path, survivor_id: str, merged_id: str, reason: str) -> dict:
    root = Path(root)
    _validate_object_id(survivor_id)
    _validate_object_id(merged_id)
    reason = _validate_reason(reason)
    if survivor_id == merged_id:
        raise ValueError("survivor_id and merged_id must differ")

    _is_active_endpoint(root, survivor_id)
    _is_active_endpoint(root, merged_id)

    survivor, survivor_entry = _load_current(root, survivor_id)
    merged, merged_entry = _load_current(root, merged_id)

    merged_record = copy.deepcopy(merged)
    if merged_entry.get("canon_membership") == "active":
        merged_record["canon_membership"] = "stale"
    merged_record["status"] = "tombstoned"
    merged_record["merge_reason"] = reason
    merged_record["merged_into"] = survivor_id
    merged_record["revision"] = _next_revision(merged_record.get("revision"))
    merged_record["updated_at"] = _now()

    survivor_record = copy.deepcopy(survivor)
    if survivor_entry.get("canon_membership") == "active":
        survivor_record["canon_membership"] = "stale"
    survivor_record["revision"] = _next_revision(survivor_record.get("revision"))
    survivor_record["updated_at"] = _now()

    for relation in _effective_relations(root):
        if relation.get("status") != "active":
            continue
        if relation.get("source_id") == merged_id or relation.get("target_id") == merged_id:
            _replace_relation_endpoints_for_merge(
                root, relation, survivor_id, merged_id
            )

    merged_history = _history_with_new_revision(merged_entry, merged_record["revision"])
    _publish(
        root,
        merged_record,
        merged_history,
        tombstoned=True,
        merged_into=survivor_id,
        merged_from=merged_entry.get("merged_from", []),
    )

    survivor_merged_from = list(survivor_entry.get("merged_from", []))
    if merged_id not in survivor_merged_from:
        survivor_merged_from.append(merged_id)
    survivor_history = _history_with_new_revision(
        survivor_entry, survivor_record["revision"]
    )
    return _publish(
        root,
        survivor_record,
        survivor_history,
        tombstoned=bool(survivor_entry.get("tombstoned", False)),
        merged_into=survivor_entry.get("merged_into"),
        merged_from=survivor_merged_from,
    )


def add_relation(
    root: Path,
    source_id: str,
    relation: str,
    target_id: str,
    evidence: dict | None = None,
) -> dict:
    root = Path(root)
    _validate_object_id(source_id)
    _validate_object_id(target_id)
    if source_id == target_id:
        raise ValueError("source_id and target_id must differ")
    if relation not in RELATION_VALUES:
        raise ValueError(f"relation must be one of {RELATION_VALUES}")
    if evidence is not None and not isinstance(evidence, dict):
        raise ValueError("evidence must be a dict or None")

    _is_active_endpoint(root, source_id)
    _is_active_endpoint(root, target_id)

    relation_id = allocate_id(root, "relation")
    now = _now()
    record = {
        "relation_id": relation_id,
        "source_id": source_id,
        "relation": relation,
        "target_id": target_id,
        "evidence": copy.deepcopy(evidence),
        "revision": "rev-0001",
        "status": "active",
        "supersedes": None,
        "created_at": now,
    }
    return _append_relation_record(root, record)