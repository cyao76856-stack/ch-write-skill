"""Project validation gates for CH-Write projects.

Validation is read-only.  It inspects current indexes, append-only logs,
version manifests and source records, then returns a list of issues.  Every
issue has at least ``code``, ``severity`` and ``message``.  Only missing
inputs, missing reasons, unconfirmed canon, source conflicts, corrupted files
and permission/security problems are reported as ``gate``.
"""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from .constants import DECISION_STATUS_VALUES, FILE_STATUS_VALUES, ID_PREFIXES, LIST_LEVELS
from .graph import impact
from .io import read_json, read_jsonl
from .objects import RELATION_VALUES, effective_relations
from .lists import LIST_CATEGORIES
from .worlddata import _LOCATION_REQUIRED, _TIMELINE_REQUIRED
from .sources import compute_digest

GATE = "gate"
WARN = "warn"
INFO = "info"

_OBJECT_ID_PATTERN = re.compile(r"^([A-Z]{3})-([0-9]{4,})$")
_REVISION_PATTERN = re.compile(r"^rev-[0-9]{4,}$")
_VERSION_PATTERN = re.compile(r"^v[0-9]{3,}$")
_DECISION_ID_PATTERN = re.compile(r"^DEC-[0-9]{4,}$")
_CHANGE_ID_PATTERN = re.compile(r"^CHG-[0-9]{4,}$")
_SOURCE_ID_PATTERN = re.compile(r"^SRC-[0-9]{4,}$")

_DECISION_EVENT_TO_STATUS = {
    "proposed": "pending",
    "confirmed": "confirmed",
    "rejected": "rejected",
    "withdrawn": "withdrawn",
    "superseded": "superseded",
    "waived": "waived",
}

_FILE_STATUS_OVERRIDES = ("pending", "rejected", "withdrawn", "superseded")


def _issue(code: str, severity: str, message: str, location: str | None = None, **details) -> dict:
    item = {"code": code, "severity": severity, "message": message}
    if location is not None:
        item["path"] = location
    item.update(details)
    return item


def _read_json_checked(root: Path, relative_path: str, issues: list[dict], required: bool = False):
    path = Path(root) / relative_path
    try:
        return read_json(path)
    except FileNotFoundError:
        if required:
            issues.append(
                _issue(
                    "missing_required_file",
                    GATE,
                    f"required file is missing: {relative_path}",
                    relative_path,
                )
            )
        return None
    except (OSError, ValueError) as exc:
        issues.append(
            _issue(
                "file_corrupt",
                GATE,
                f"file cannot be read or is not a JSON object: {relative_path}: {exc}",
                relative_path,
            )
        )
        return None


def _read_jsonl_checked(root: Path, relative_path: str, issues: list[dict]) -> list[dict] | None:
    path = Path(root) / relative_path
    try:
        return read_jsonl(path)
    except (OSError, ValueError) as exc:
        issues.append(
            _issue(
                "file_corrupt",
                GATE,
                f"JSONL file cannot be read: {relative_path}: {exc}",
                relative_path,
            )
        )
        return None


def _load_entities(root: Path, issues: list[dict]) -> dict | None:
    data = _read_json_checked(root, "indexes/entities.json", issues)
    if data is None:
        return {}
    objects = data.get("objects")
    if not isinstance(objects, dict):
        issues.append(
            _issue(
                "invalid_entities_index",
                GATE,
                "indexes/entities.json does not contain an objects object",
                "indexes/entities.json",
            )
        )
        return {}
    return objects


def _load_relation_index(root: Path, issues: list[dict]) -> list[dict] | None:
    data = _read_json_checked(root, "indexes/relations.json", issues)
    if data is None:
        return None
    relations = data.get("relations")
    if not isinstance(relations, list):
        issues.append(
            _issue(
                "invalid_relations_index",
                GATE,
                "indexes/relations.json does not contain a relations list",
                "indexes/relations.json",
            )
        )
        return None
    return relations


def _load_project(root: Path, issues: list[dict]) -> dict | None:
    data = _read_json_checked(root, "project.json", issues, required=True)
    if data is None:
        return None
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        issues.append(
            _issue(
                "project_missing_name",
                GATE,
                "project.json must contain a non-empty name",
                "project.json",
            )
        )
    return data

def _validate_list_files(root: Path, issues: list[dict]) -> None:
    """Validate ``store/lists/*.json`` as JSON objects with valid item arrays."""
    lists_dir = Path(root) / "store" / "lists"
    if not lists_dir.exists():
        return

    for path in sorted(lists_dir.glob("*.json")):
        category = path.stem
        relative_path = path.relative_to(root).as_posix()
        data = _read_json_checked(root, relative_path, issues)
        if data is None:
            continue

        if category not in LIST_CATEGORIES:
            issues.append(
                _issue(
                    "unknown_list_category",
                    GATE,
                    f"list file has unknown category: {category}",
                    relative_path,
                    category=category,
                )
            )
            continue

        items = data.get("items")
        if not isinstance(items, list):
            issues.append(
                _issue(
                    "invalid_list_master_data",
                    GATE,
                    f"list master data does not contain an items array: {relative_path}",
                    relative_path,
                )
            )
            continue

        seen_ids = set()
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                issues.append(
                    _issue(
                        "invalid_list_item",
                        GATE,
                        f"list item at index {index} is not an object",
                        relative_path,
                        index=index,
                    )
                )
                continue

            item_id = item.get("id")
            name = item.get("name")
            if not isinstance(item_id, str) or not item_id.strip():
                issues.append(
                    _issue(
                        "list_item_missing_id",
                        GATE,
                        f"list item at index {index} is missing a non-empty id",
                        relative_path,
                        index=index,
                    )
                )
            elif item_id in seen_ids:
                issues.append(
                    _issue(
                        "duplicate_list_item_id",
                        GATE,
                        f"list item id {item_id!r} appears more than once",
                        relative_path,
                        index=index,
                        id=item_id,
                    )
                )
            if isinstance(item_id, str):
                seen_ids.add(item_id)

            if not isinstance(name, str) or not name.strip():
                issues.append(
                    _issue(
                        "list_item_missing_name",
                        GATE,
                        f"list item at index {index} is missing a non-empty name",
                        relative_path,
                        index=index,
                    )
                )

            if "category" in item and item.get("category") != category:
                issues.append(
                    _issue(
                        "list_item_category_mismatch",
                        GATE,
                        f"list item at index {index} has category {item.get('category')!r}",
                        relative_path,
                        index=index,
                    )
                )

            level = item.get("level")
            if level is not None and level not in LIST_LEVELS:
                issues.append(
                    _issue(
                        "invalid_list_item_level",
                        GATE,
                        f"list item at index {index} has invalid level: {level!r}",
                        relative_path,
                        index=index,
                    )
                )


def _validate_worlddata_log(
    root: Path,
    relative_path: str,
    required_fields: tuple[str, ...],
    issue_code: str,
    issues: list[dict],
) -> None:
    records = _read_jsonl_checked(root, relative_path, issues)
    if records is None:
        return

    id_field = required_fields[0]
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            issues.append(
                _issue(
                    issue_code,
                    GATE,
                    f"worlddata log contains a non-object record at index {index}",
                    relative_path,
                    index=index,
                )
            )
            continue

        missing = [field for field in required_fields if field not in record]
        if missing:
            issues.append(
                _issue(
                    issue_code,
                    GATE,
                    f"worlddata record at index {index} is missing required fields: {missing!r}",
                    relative_path,
                    index=index,
                    missing=missing,
                )
            )

        record_id = record.get(id_field)
        if not isinstance(record_id, str) or not record_id.strip():
            issues.append(
                _issue(
                    issue_code,
                    GATE,
                    f"worlddata record at index {index} has invalid {id_field}: {record_id!r}",
                    relative_path,
                    index=index,
                )
            )


def _load_object_logs(root: Path, issues: list[dict]) -> list[dict]:
    records = []
    objects_dir = Path(root) / "store" / "objects"
    if not objects_dir.exists():
        return records
    for path in sorted(objects_dir.glob("*.jsonl")):
        values = _read_jsonl_checked(root, path.relative_to(root).as_posix(), issues)
        if values is not None:
            records.extend(values)
    return records


def _load_version_index(root: Path, issues: list[dict]) -> dict | None:
    data = _read_json_checked(root, "indexes/versions.json", issues)
    if data is None:
        return None
    versions = data.get("versions")
    if versions is None:
        return data
    if not isinstance(versions, dict):
        issues.append(
            _issue(
                "invalid_versions_index",
                GATE,
                "indexes/versions.json does not contain a versions object",
                "indexes/versions.json",
            )
        )
        return None
    return data


def _revision_exists_in_records(
    object_id: str,
    revision: str,
    object_log_records: list[dict],
    relation_log_records: list[dict] | None,
) -> bool:
    match = _OBJECT_ID_PATTERN.fullmatch(object_id)
    if match is None:
        return False
    prefix = match.group(1)
    object_type = next(
        (name for name, candidate in ID_PREFIXES.items() if candidate == prefix),
        None,
    )
    if object_type is None:
        return False

    if object_type == "relation":
        return any(
            record.get("relation_id") == object_id
            and record.get("revision") == revision
            for record in (relation_log_records or [])
        )

    return any(
        record.get("object_id") == object_id
        and record.get("type") == object_type
        and record.get("revision") == revision
        for record in object_log_records
    )


def _object_is_active(entry: dict | None) -> bool:
    if not isinstance(entry, dict):
        return False
    if entry.get("tombstoned") or entry.get("merged_into") is not None:
        return False
    if entry.get("status") in ("tombstoned", "merged"):
        return False
    return True


def _validate_relation_record(
    relation: dict,
    entities: dict | None,
    issues: list[dict],
    path: str = "indexes/relations.json",
) -> None:
    relation_id = relation.get("relation_id")
    source_id = relation.get("source_id")
    target_id = relation.get("target_id")
    relation_name = relation.get("relation")

    if not isinstance(relation_id, str) or _OBJECT_ID_PATTERN.fullmatch(relation_id) is None:
        issues.append(
            _issue(
                "invalid_relation_id",
                GATE,
                f"relation record has invalid relation_id: {relation_id!r}",
                path,
            )
        )
        return

    if not isinstance(relation_name, str) or relation_name not in RELATION_VALUES:
        issues.append(
            _issue(
                "invalid_relation_value",
                GATE,
                f"relation {relation_id} has invalid relation: {relation_name!r}",
                path,
                relation_id=relation_id,
            )
        )

    if not isinstance(source_id, str) or _OBJECT_ID_PATTERN.fullmatch(source_id) is None:
        issues.append(
            _issue(
                "invalid_relation_source",
                GATE,
                f"relation {relation_id} has invalid source_id: {source_id!r}",
                path,
                relation_id=relation_id,
            )
        )
    if not isinstance(target_id, str) or _OBJECT_ID_PATTERN.fullmatch(target_id) is None:
        issues.append(
            _issue(
                "invalid_relation_target",
                GATE,
                f"relation {relation_id} has invalid target_id: {target_id!r}",
                path,
                relation_id=relation_id,
            )
        )
        return

    if entities is not None:
        source_entry = entities.get(source_id)
        target_entry = entities.get(target_id)
        if not isinstance(source_entry, dict):
            issues.append(
                _issue(
                    "relation_missing_source",
                    GATE,
                    f"relation {relation_id} references missing source object {source_id}",
                    path,
                    relation_id=relation_id,
                    object_id=source_id,
                )
            )
        if not isinstance(target_entry, dict):
            issues.append(
                _issue(
                    "relation_missing_target",
                    GATE,
                    f"relation {relation_id} references missing target object {target_id}",
                    path,
                    relation_id=relation_id,
                    object_id=target_id,
                )
            )
            return
        if not _object_is_active(source_entry):
            issues.append(
                _issue(
                    "relation_tombstoned_source",
                    GATE,
                    f"active relation {relation_id} references tombstoned source {source_id}",
                    path,
                    relation_id=relation_id,
                    object_id=source_id,
                )
            )
        if not _object_is_active(target_entry):
            issues.append(
                _issue(
                    "relation_tombstoned_target",
                    GATE,
                    f"active relation {relation_id} references tombstoned target {target_id}",
                    path,
                    relation_id=relation_id,
                    object_id=target_id,
                )
            )

def _validate_object_records(records: list[dict], entities: dict | None, issues: list[dict]) -> None:
    revision_counter = Counter()
    for record in records:
        object_id = record.get("object_id")
        revision = record.get("revision")
        object_type = record.get("type")
        if isinstance(object_id, str) and isinstance(revision, str):
            revision_counter[(object_id, revision)] += 1

        if not isinstance(object_id, str) or _OBJECT_ID_PATTERN.fullmatch(object_id) is None:
            issues.append(
                _issue(
                    "invalid_object_id",
                    GATE,
                    f"object log contains invalid object_id: {object_id!r}",
                    "store/objects",
                )
            )
        if not isinstance(object_type, str) or object_type not in ID_PREFIXES:
            issues.append(
                _issue(
                    "invalid_object_type",
                    GATE,
                    f"object log contains invalid type for {object_id!r}: {object_type!r}",
                    "store/objects",
                    object_id=object_id,
                )
            )
        if not isinstance(revision, str) or _REVISION_PATTERN.fullmatch(revision) is None:
            issues.append(
                _issue(
                    "invalid_object_revision",
                    GATE,
                    f"object {object_id!r} has invalid revision: {revision!r}",
                    "store/objects",
                    object_id=object_id,
                )
            )

    for (object_id, revision), count in revision_counter.items():
        if count > 1:
            issues.append(
                _issue(
                    "duplicate_object_revision",
                    GATE,
                    f"object {object_id} revision {revision} appears {count} times",
                    "store/objects",
                    object_id=object_id,
                    revision=revision,
                )
            )


def _validate_entities(entities: dict, object_log_records: list[dict], issues: list[dict]) -> None:
    for object_id, entry in entities.items():
        if not isinstance(object_id, str) or _OBJECT_ID_PATTERN.fullmatch(object_id) is None:
            issues.append(
                _issue(
                    "invalid_object_id",
                    GATE,
                    f"entities index contains invalid object_id: {object_id!r}",
                    "indexes/entities.json",
                )
            )
            continue
        if not isinstance(entry, dict):
            issues.append(
                _issue(
                    "invalid_entity",
                    GATE,
                    f"entities index entry for {object_id} is not an object",
                    "indexes/entities.json",
                    object_id=object_id,
                )
            )
            continue

        if entry.get("object_id") not in (None, object_id):
            issues.append(
                _issue(
                    "entity_object_id_mismatch",
                    GATE,
                    f"entities index entry for {object_id} has object_id {entry.get('object_id')!r}",
                    "indexes/entities.json",
                    object_id=object_id,
                )
            )

        object_type = entry.get("type")
        if not isinstance(object_type, str) or object_type not in ID_PREFIXES:
            issues.append(
                _issue(
                    "invalid_object_type",
                    GATE,
                    f"entity {object_id} has invalid type: {object_type!r}",
                    "indexes/entities.json",
                    object_id=object_id,
                )
            )

        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            issues.append(
                _issue(
                    "object_missing_name",
                    GATE,
                    f"entity {object_id} is missing a non-empty name",
                    "indexes/entities.json",
                    object_id=object_id,
                )
            )

        decision_status = entry.get("decision_status")
        if (
            entry.get("canon_membership") == "active"
            and isinstance(decision_status, str)
            and decision_status in _FILE_STATUS_OVERRIDES
        ):
            issues.append(
                _issue(
                    "canon_has_non_confirmed_status",
                    GATE,
                    f"entity {object_id} is active canon but decision_status is {decision_status!r}",
                    "indexes/entities.json",
                    object_id=object_id,
                )
            )

        revision = entry.get("revision")
        if not isinstance(revision, str) or _REVISION_PATTERN.fullmatch(revision) is None:
            issues.append(
                _issue(
                    "object_missing_revision",
                    GATE,
                    f"entity {object_id} has invalid revision: {revision!r}",
                    "indexes/entities.json",
                    object_id=object_id,
                )
            )
        elif not any(
            record.get("object_id") == object_id and record.get("revision") == revision
            for record in object_log_records
        ):
            issues.append(
                _issue(
                    "entity_revision_missing",
                    GATE,
                    f"entity {object_id} revision {revision} does not exist in object logs",
                    "indexes/entities.json",
                    object_id=object_id,
                    revision=revision,
                )
            )


def _validate_relation_log(records: list[dict], issues: list[dict]) -> None:
    relation_ids = Counter()
    for record in records:
        if not isinstance(record, dict):
            issues.append(
                _issue(
                    "malformed_relation_record",
                    GATE,
                    "relation log contains a non-object record",
                    "store/relations.jsonl",
                )
            )
            continue

        relation_id = record.get("relation_id")
        source_id = record.get("source_id")
        target_id = record.get("target_id")
        supersedes = record.get("supersedes")
        relation_name = record.get("relation")

        malformed = False
        if not isinstance(relation_id, str) or not relation_id:
            malformed = True
        if not isinstance(source_id, str) or not source_id:
            malformed = True
        if not isinstance(target_id, str) or not target_id:
            malformed = True
        if supersedes is not None and not isinstance(supersedes, str):
            malformed = True
        if not isinstance(relation_name, str) or relation_name not in RELATION_VALUES:
            malformed = True

        if malformed:
            issues.append(
                _issue(
                    "malformed_relation_record",
                    GATE,
                    f"relation log contains a malformed record: {record!r}",
                    "store/relations.jsonl",
                )
            )
            continue

        relation_ids[relation_id] += 1

    for relation_id, count in relation_ids.items():
        if count > 1:
            issues.append(
                _issue(
                    "duplicate_relation_id",
                    GATE,
                    f"relation id {relation_id} appears {count} times in relations.jsonl",
                    "store/relations.jsonl",
                    relation_id=relation_id,
                )
            )

def _validate_decisions(
    decisions,
    decision_events: list[dict] | None,
    valid_references: set[str],
    issues: list[dict],
) -> None:
    if not isinstance(decisions, dict):
        issues.append(
            _issue(
                "invalid_decisions_index",
                GATE,
                "indexes/decisions.json must contain a decisions object",
                "indexes/decisions.json",
            )
        )
        return

    derived_status = {}
    if decision_events is not None:
        for event in decision_events:
            if not isinstance(event, dict):
                issues.append(
                    _issue(
                        "malformed_decision_event",
                        GATE,
                        "decision log contains a non-object event",
                        "logs/decisions.jsonl",
                    )
                )
                continue
            decision_id = event.get("decision_id")
            event_type = event.get("event_type")
            if not isinstance(event_type, str):
                issues.append(
                    _issue(
                        "malformed_decision_event",
                        GATE,
                        f"decision log contains an event with malformed event_type: {event_type!r}",
                        "logs/decisions.jsonl",
                    )
                )
                continue
            if isinstance(decision_id, str) and event_type in _DECISION_EVENT_TO_STATUS:
                derived_status[decision_id] = _DECISION_EVENT_TO_STATUS[event_type]

    for decision_id, decision in decisions.items():
        if not isinstance(decision_id, str) or _DECISION_ID_PATTERN.fullmatch(decision_id) is None:
            issues.append(
                _issue(
                    "invalid_decision_id",
                    GATE,
                    f"decisions index contains invalid decision_id: {decision_id!r}",
                    "indexes/decisions.json",
                )
            )
            continue
        if not isinstance(decision, dict):
            issues.append(
                _issue(
                    "invalid_decision",
                    GATE,
                    f"decision {decision_id} is not an object",
                    "indexes/decisions.json",
                    decision_id=decision_id,
                )
            )
            continue

        status = decision.get("status")
        if not isinstance(status, str) or status not in DECISION_STATUS_VALUES:
            issues.append(
                _issue(
                    "invalid_decision_status",
                    GATE,
                    f"decision {decision_id} has invalid status: {status!r}",
                    "indexes/decisions.json",
                    decision_id=decision_id,
                )
            )

        if decision_id in derived_status and status != derived_status[decision_id]:
            issues.append(
                _issue(
                    "decision_index_conflict",
                    GATE,
                    f"decision {decision_id} index status {status!r} conflicts with log status {derived_status[decision_id]!r}",
                    "indexes/decisions.json",
                    decision_id=decision_id,
                )
            )

        canon_items = decision.get("canon_items")
        if (
            isinstance(canon_items, list)
            and canon_items
            and status != "confirmed"
        ):
            issues.append(
                _issue(
                    "canon_has_non_confirmed_status",
                    GATE,
                    f"decision {decision_id} has canon_items but status is {status!r}",
                    "indexes/decisions.json",
                    decision_id=decision_id,
                )
            )

        if status == "confirmed":
            main_reason = decision.get("main_reason")
            if not isinstance(main_reason, str) or not main_reason.strip():
                issues.append(
                    _issue(
                        "confirmed_decision_missing_reason",
                        GATE,
                        f"confirmed decision {decision_id} is missing main_reason",
                        "indexes/decisions.json",
                        decision_id=decision_id,
                    )
                )
            author_statement = decision.get("author_statement")
            if not isinstance(author_statement, str) or not author_statement.strip():
                issues.append(
                    _issue(
                        "confirmed_decision_missing_confirmation",
                        GATE,
                        f"confirmed decision {decision_id} is missing author_statement",
                        "indexes/decisions.json",
                        decision_id=decision_id,
                    )
                )

        for field_name in ("affected_objects", "canon_items"):
            values = decision.get(field_name, [])
            if not isinstance(values, list):
                continue
            for referenced_id in values:
                if not isinstance(referenced_id, str):
                    continue
                if _OBJECT_ID_PATTERN.fullmatch(referenced_id) is None:
                    continue
                if referenced_id not in valid_references:
                    issues.append(
                        _issue(
                            "decision_missing_object_reference",
                            GATE,
                            f"decision {decision_id} {field_name} references missing object or relation {referenced_id}",
                            "indexes/decisions.json",
                            decision_id=decision_id,
                            object_id=referenced_id,
                        )
                    )

def _validate_changes(
    records: list[dict],
    valid_references: set[str],
    issues: list[dict],
) -> None:
    change_ids = set()
    for record in records:
        change_id = record.get("change_id")
        if not isinstance(change_id, str) or _CHANGE_ID_PATTERN.fullmatch(change_id) is None:
            issues.append(
                _issue(
                    "invalid_change_id",
                    GATE,
                    f"change log contains invalid change_id: {change_id!r}",
                    "logs/changes.jsonl",
                )
            )
        else:
            if change_id in change_ids:
                issues.append(
                    _issue(
                        "duplicate_change_id",
                        GATE,
                        f"change id {change_id} appears more than once",
                        "logs/changes.jsonl",
                        change_id=change_id,
                    )
                )
            change_ids.add(change_id)

        confirmation_status = record.get("confirmation_status")
        if (
            not isinstance(confirmation_status, str)
            or confirmation_status not in DECISION_STATUS_VALUES
        ):
            issues.append(
                _issue(
                    "invalid_change_confirmation_status",
                    GATE,
                    f"change {change_id!r} has invalid confirmation_status: {confirmation_status!r}",
                    "logs/changes.jsonl",
                    change_id=change_id,
                )
            )

        related_objects = record.get("related_objects", [])
        if isinstance(related_objects, list):
            for referenced_id in related_objects:
                if (
                    isinstance(referenced_id, str)
                    and _OBJECT_ID_PATTERN.fullmatch(referenced_id)
                    and referenced_id not in valid_references
                ):
                    issues.append(
                        _issue(
                            "change_missing_object_reference",
                            GATE,
                            f"change {change_id!r} references missing object or relation {referenced_id}",
                            "logs/changes.jsonl",
                            change_id=change_id,
                            object_id=referenced_id,
                        )
                    )

def _validate_sources(
    root: Path,
    sources: list[dict],
    active_manifest: dict | None,
    issues: list[dict],
) -> None:
    source_ids = set()
    for source in sources:
        if not isinstance(source, dict):
            issues.append(
                _issue(
                    "invalid_source",
                    GATE,
                    "sources index contains a non-object entry",
                    "indexes/sources.json",
                )
            )
            continue

        source_id = source.get("source_id")
        path = source.get("path")
        if not isinstance(source_id, str) or _SOURCE_ID_PATTERN.fullmatch(source_id) is None:
            issues.append(
                _issue(
                    "invalid_source_id",
                    GATE,
                    f"source record has invalid source_id: {source_id!r}",
                    "indexes/sources.json",
                )
            )
        else:
            if source_id in source_ids:
                issues.append(
                    _issue(
                        "duplicate_source_id",
                        GATE,
                        f"source id {source_id} appears more than once",
                        "indexes/sources.json",
                        source_id=source_id,
                    )
                )
            source_ids.add(source_id)

        if not isinstance(path, str) or not path:
            issues.append(
                _issue(
                    "source_missing_path",
                    GATE,
                    f"source {source_id!r} is missing a path",
                    "indexes/sources.json",
                    source_id=source_id,
                )
            )
            continue

        source_path = Path(path)
        if not source_path.is_file():
            issues.append(
                _issue(
                    "source_missing",
                    GATE,
                    f"source {source_id} file is missing: {path}",
                    "indexes/sources.json",
                    source_id=source_id,
                    path=path,
                )
            )
            continue

        stored_digest = source.get("digest")
        if isinstance(stored_digest, str):
            try:
                current_digest = compute_digest(source_path)
            except OSError as exc:
                issues.append(
                    _issue(
                        "source_unreadable",
                        GATE,
                        f"source {source_id} cannot be read: {path}: {exc}",
                        "indexes/sources.json",
                        source_id=source_id,
                        path=path,
                    )
                )
                continue
            if current_digest != stored_digest:
                issues.append(
                    _issue(
                        "source_conflict",
                        GATE,
                        f"source {source_id} changed since registration: {path}",
                        "indexes/sources.json",
                        source_id=source_id,
                        path=path,
                    )
                )

    if active_manifest is not None:
        manifest_sources = active_manifest.get("source_versions")
        if isinstance(manifest_sources, dict):
            current_sources = {
                source.get("source_id"): source
                for source in sources
                if isinstance(source, dict)
            }
            for source_id, expected in manifest_sources.items():
                if not isinstance(expected, dict):
                    issues.append(
                        _issue(
                            "invalid_manifest_source_version",
                            GATE,
                            f"active version source {source_id} has a non-object source_versions entry",
                            "versions/*/manifest.json",
                            source_id=source_id,
                        )
                    )
                    continue
                current = current_sources.get(source_id)
                if not isinstance(current, dict):
                    issues.append(
                        _issue(
                            "active_canon_source_missing",
                            GATE,
                            f"active version references missing source {source_id}",
                            "versions/*/manifest.json",
                            source_id=source_id,
                        )
                    )
                    continue
                current_digest = current.get("digest")
                if expected.get("digest") != current_digest:
                    issues.append(
                        _issue(
                            "active_canon_source_mismatch",
                            GATE,
                            f"active version source {source_id} does not match current source index",
                            "versions/*/manifest.json",
                            source_id=source_id,
                        )
                    )


def _validate_versions(
    root: Path,
    project: dict | None,
    versions: dict[str, dict],
    version_index: dict | None,
    object_log_records: list[dict],
    relation_log_records: list[dict] | None,
    issues: list[dict],
) -> None:
    active_version = None
    if project is not None:
        active_version = project.get("active_version")
        if active_version is not None:
            if not isinstance(active_version, str) or _VERSION_PATTERN.fullmatch(active_version) is None:
                issues.append(
                    _issue(
                        "invalid_active_version",
                        GATE,
                        f"project.json has invalid active_version: {active_version!r}",
                        "project.json",
                    )
                )
                active_version = None
            elif active_version not in versions:
                issues.append(
                    _issue(
                        "active_version_manifest_missing",
                        GATE,
                        f"active version {active_version} has no manifest",
                        "project.json",
                        version=active_version,
                    )
                )

    version_index_versions = {}
    if version_index is not None:
        raw = version_index.get("versions")
        if isinstance(raw, dict):
            version_index_versions = raw

    for version, manifest in versions.items():
        path = f"versions/{version}/manifest.json"

        if manifest is None:
            issues.append(
                _issue(
                    "manifest_corrupt",
                    GATE,
                    f"version manifest cannot be read: {path}",
                    path,
                    version=version,
                )
            )
            continue

        if manifest.get("version") != version:
            issues.append(
                _issue(
                    "manifest_version_mismatch",
                    GATE,
                    f"manifest version {manifest.get('version')!r} does not match directory {version}",
                    path,
                    version=version,
                )
            )

        status = manifest.get("status")
        if status is not None and (
            not isinstance(status, str) or status not in FILE_STATUS_VALUES
        ):
            issues.append(
                _issue(
                    "invalid_manifest_status",
                    GATE,
                    f"manifest for {version} has invalid status: {status!r}",
                    path,
                    version=version,
                )
            )
        if isinstance(status, str) and status in _FILE_STATUS_OVERRIDES:
            issues.append(
                _issue(
                    "canon_has_non_confirmed_status",
                    GATE,
                    f"canon version {version} has non-confirmed status {status!r}",
                    path,
                    version=version,
                )
            )

        parent = manifest.get("parent")
        if parent is not None and (
            not isinstance(parent, str) or _VERSION_PATTERN.fullmatch(parent) is None
        ):
            issues.append(
                _issue(
                    "invalid_manifest_parent",
                    GATE,
                    f"manifest for {version} has invalid parent: {parent!r}",
                    path,
                    version=version,
                )
            )
        elif isinstance(parent, str) and parent not in versions:
            issues.append(
                _issue(
                    "manifest_parent_missing",
                    GATE,
                    f"manifest for {version} references missing parent {parent}",
                    path,
                    version=version,
                    parent=parent,
                )
            )

        objects = manifest.get("objects")
        if not isinstance(objects, dict):
            issues.append(
                _issue(
                    "manifest_missing_objects",
                    GATE,
                    f"manifest for {version} is missing objects mapping",
                    path,
                    version=version,
                )
            )
            objects = {}

        for object_id, revision in objects.items():
            if not isinstance(object_id, str) or _OBJECT_ID_PATTERN.fullmatch(object_id) is None:
                issues.append(
                    _issue(
                        "manifest_invalid_object_id",
                        GATE,
                        f"manifest for {version} contains invalid object_id: {object_id!r}",
                        path,
                        version=version,
                    )
                )
                continue
            if not isinstance(revision, str) or _REVISION_PATTERN.fullmatch(revision) is None:
                issues.append(
                    _issue(
                        "manifest_invalid_revision",
                        GATE,
                        f"manifest for {version} has invalid revision for {object_id}: {revision!r}",
                        path,
                        version=version,
                        object_id=object_id,
                    )
                )
                continue
            if not _revision_exists_in_records(
                object_id, revision, object_log_records, relation_log_records
            ):
                issues.append(
                    _issue(
                        "manifest_missing_revision",
                        GATE,
                        f"manifest for {version} references missing revision {object_id}@{revision}",
                        path,
                        version=version,
                        object_id=object_id,
                        revision=revision,
                    )
                )

        stale = manifest.get("stale")
        if version == active_version and isinstance(stale, list):
            for stale_item in stale:
                stale_id = stale_item if isinstance(stale_item, str) else (
                    stale_item.get("object_id") if isinstance(stale_item, dict) else None
                )
                if isinstance(stale_id, str) and stale_id in objects:
                    issues.append(
                        _issue(
                            "stale_in_active_canon",
                            GATE,
                            f"stale object {stale_id} appears in active canon {version}",
                            path,
                            version=version,
                            object_id=stale_id,
                        )
                    )

        indexed = version_index_versions.get(version)
        if isinstance(indexed, dict):
            indexed_status = indexed.get("status")
            if indexed_status is not None and (
                not isinstance(indexed_status, str)
                or indexed_status not in FILE_STATUS_VALUES
            ):
                issues.append(
                    _issue(
                        "invalid_version_status",
                        GATE,
                        f"version {version} has invalid index status: {indexed_status!r}",
                        path,
                        version=version,
                    )
                )
            if isinstance(indexed_status, str) and indexed_status in _FILE_STATUS_OVERRIDES:
                issues.append(
                    _issue(
                        "canon_has_non_confirmed_status",
                        GATE,
                        f"canon version {version} has non-confirmed index status {indexed_status!r}",
                        path,
                        version=version,
                    )
                )
            if indexed_status == "tampered":
                issues.append(
                    _issue(
                        "version_tampered",
                        GATE,
                        f"version {version} is marked as tampered",
                        path,
                        version=version,
                    )
                )
            files = indexed.get("files")
            if isinstance(files, dict):
                for file_path, file_status in files.items():
                    if isinstance(file_status, dict) and file_status.get("status") == "tampered":
                        issues.append(
                            _issue(
                                "version_tampered",
                                GATE,
                                f"version file is marked as tampered: {file_path}",
                                file_path,
                                version=version,
                            )
                        )

def _load_versions(root: Path, issues: list[dict]) -> dict[str, dict]:
    versions_dir = Path(root) / "versions"
    versions = {}
    if not versions_dir.exists():
        return versions

    for path in sorted(versions_dir.iterdir(), key=lambda item: item.name):
        if not path.is_dir() or _VERSION_PATTERN.fullmatch(path.name) is None:
            continue
        version = path.name
        manifest_path = path / "manifest.json"
        if not manifest_path.exists():
            issues.append(
                _issue(
                    "manifest_missing",
                    GATE,
                    f"version directory exists without manifest.json: versions/{version}",
                    f"versions/{version}",
                    version=version,
                )
            )
            versions[version] = None
            continue
        versions[version] = _read_json_checked(root, f"versions/{version}/manifest.json", issues)
    return versions


def _unique_issues(issues: list[dict]) -> list[dict]:
    unique = []
    seen = set()
    for item in issues:
        key = (
            item.get("code"),
            item.get("severity"),
            item.get("message"),
            item.get("path"),
            tuple(sorted(
                (detail_key, str(detail_value))
                for detail_key, detail_value in item.items()
                if detail_key not in ("code", "severity", "message", "path")
            )),
        )
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def validate_project(root: Path) -> list[dict]:
    """Validate a CH-Write project and return issues as a list of dicts."""
    root = Path(root)
    issues: list[dict] = []

    project = _load_project(root, issues)
    entities = _load_entities(root, issues)
    if not isinstance(entities, dict):
        entities = {}
    object_log_records = _load_object_logs(root, issues)
    relation_log = _read_jsonl_checked(root, "store/relations.jsonl", issues) or []
    relation_index_path = Path(root) / "indexes" / "relations.json"
    relation_index_missing = not relation_index_path.exists()
    relation_index = _load_relation_index(root, issues)
    decisions = _read_json_checked(root, "indexes/decisions.json", issues) or {}
    decision_events = _read_jsonl_checked(root, "logs/decisions.jsonl", issues)
    changes = _read_jsonl_checked(root, "logs/changes.jsonl", issues) or []
    sources_data = _read_json_checked(root, "indexes/sources.json", issues) or {}
    sources = sources_data.get("sources") if isinstance(sources_data, dict) else None
    versions = _load_versions(root, issues)
    version_index = _load_version_index(root, issues)

    _validate_object_records(object_log_records, entities, issues)
    _validate_entities(entities, object_log_records, issues)
    _validate_list_files(root, issues)
    _validate_worlddata_log(root, "store/timeline.jsonl", _TIMELINE_REQUIRED, "invalid_timeline_record", issues)
    _validate_worlddata_log(root, "store/location_states.jsonl", _LOCATION_REQUIRED, "invalid_location_state_record", issues)

    if relation_log is not None:
        _validate_relation_log(relation_log, issues)

    relation_ids = set()
    active_relations = []
    relation_validation_path = "indexes/relations.json"
    if relation_index is not None:
        relation_ids = {
            relation.get("relation_id")
            for relation in relation_index
            if isinstance(relation, dict) and isinstance(relation.get("relation_id"), str)
        }
        active_relations.extend(
            relation for relation in relation_index
            if isinstance(relation, dict) and relation.get("status") == "active"
        )
    elif relation_log:
        relation_validation_path = "store/relations.jsonl"
        if relation_index_missing:
            issues.append(
                _issue(
                    "relation_index_missing",
                    GATE,
                    "indexes/relations.json is missing while relation history exists",
                    "indexes/relations.json",
                )
            )
        try:
            effective = effective_relations(root)
        except (OSError, ValueError) as exc:
            effective = []
            issues.append(
                _issue(
                    "relations_corrupt",
                    GATE,
                    f"effective relations cannot be built: {exc}",
                    "store/relations.jsonl",
                )
            )
        relation_ids = {
            relation.get("relation_id")
            for relation in effective
            if isinstance(relation, dict) and isinstance(relation.get("relation_id"), str)
        }
        active_relations.extend(
            relation for relation in effective
            if isinstance(relation, dict) and relation.get("status") == "active"
        )

    valid_references = set(entities) | relation_ids
    for relation in active_relations:
        _validate_relation_record(
            relation, entities, issues, path=relation_validation_path
        )

    decisions_by_id = decisions.get("decisions") if isinstance(decisions, dict) else None
    if decisions_by_id is None:
        decisions_by_id = {}
    _validate_decisions(decisions_by_id, decision_events, valid_references, issues)

    _validate_changes(changes, valid_references, issues)

    if sources is None:
        sources = []
    elif not isinstance(sources, list):
        issues.append(
            _issue(
                "invalid_sources_index",
                GATE,
                "indexes/sources.json does not contain a sources list",
                "indexes/sources.json",
            )
        )
        sources = []

    active_manifest = None
    if project is not None:
        active_version = project.get("active_version")
        if isinstance(active_version, str) and active_version in versions:
            active_manifest = versions[active_version]
    _validate_sources(root, sources, active_manifest, issues)
    _validate_versions(
        root, project, versions, version_index,
        object_log_records, relation_log, issues,
    )

    return _unique_issues(issues)
