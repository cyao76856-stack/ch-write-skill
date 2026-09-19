"""Version, proposal, stale and archive management for CH-Write projects.

The object and relation logs remain append-only.  Versions are immutable
manifests under ``versions/vNNN/manifest.json``.  They reference object
revisions already present in the append-only object logs; version directories
never contain a second copy of object data.
"""
from __future__ import annotations

import copy
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .constants import ID_PREFIXES
from .decisions import _load_decisions_index
from .io import append_jsonl, read_json, read_jsonl, write_json_atomic
from .objects import set_object_confirmed

_VERSION_PATTERN = re.compile(r"^v[0-9]{3,}$")
_REVISION_PATTERN = re.compile(r"^rev-[0-9]{4,}$")
_PROPOSAL_PATTERN = re.compile(r"^PRP-([0-9]{4,})$")
_OBJECT_ID_PATTERN = re.compile(r"^([A-Z]{3})-([0-9]{4,})$")

_FILE_STATUS_VALUES = ("draft", "reviewed", "confirmed", "immutable", "tampered")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_nonempty_string(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_string_list(value, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return list(value)


def _require_string_mapping(value, label: str) -> dict[str, str]:
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in value.items()
    ):
        raise ValueError(f"{label} must be a dict of string keys and string values")
    return dict(value)


def _proposals_index(root: Path) -> Path:
    return Path(root) / "proposals" / "index.jsonl"


def _proposals_patches_dir(root: Path) -> Path:
    return Path(root) / "proposals" / "patches"


def _proposal_patch_path(root: Path, snapshot_id: str) -> Path:
    return _proposals_patches_dir(root) / f"{snapshot_id}.json"


def _versions_dir(root: Path) -> Path:
    return Path(root) / "versions"


def _version_index_path(root: Path) -> Path:
    return Path(root) / "indexes" / "versions.json"


def _manifest_path(root: Path, version: str) -> Path:
    return _versions_dir(root) / version / "manifest.json"


def _project_path(root: Path) -> Path:
    return Path(root) / "project.json"


def _archive_dir(root: Path) -> Path:
    return Path(root) / "archive"


def _working_dir(root: Path) -> Path:
    return Path(root) / "working"


def _load_project(root: Path) -> dict:
    return read_json(_project_path(root))


def _write_project(root: Path, project: dict) -> None:
    write_json_atomic(_project_path(root), project)


def _load_entities(root: Path) -> dict:
    path = Path(root) / "indexes" / "entities.json"
    if not path.exists():
        return {}
    data = read_json(path)
    objects = data.get("objects")
    if not isinstance(objects, dict):
        raise ValueError("invalid entities index")
    return objects


def _active_object_revisions(root: Path) -> dict[str, str]:
    objects = {}
    for object_id, entry in _load_entities(root).items():
        if not isinstance(entry, dict):
            continue
        if entry.get("tombstoned") or entry.get("merged_into") is not None:
            continue
        if entry.get("status") not in (None, "active"):
            continue
        revision = entry.get("revision")
        if isinstance(revision, str):
            objects[object_id] = revision
    return objects


def _load_source_versions(root: Path) -> dict:
    path = Path(root) / "indexes" / "sources.json"
    if not path.exists():
        return {}
    data = read_json(path)
    sources = data.get("sources")
    if not isinstance(sources, list):
        raise ValueError("invalid sources index")
    result = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        source_id = source.get("source_id")
        if isinstance(source_id, str):
            result[source_id] = {
                "path": source.get("path"),
                "digest": source.get("digest"),
                "status": source.get("status"),
            }
    return result


def _read_proposals(root: Path) -> list[dict]:
    return read_jsonl(_proposals_index(root))


def _next_proposal_number(root: Path) -> int:
    numbers = []
    for record in _read_proposals(root):
        value = record.get("snapshot_id")
        if isinstance(value, str):
            match = _PROPOSAL_PATTERN.fullmatch(value)
            if match is not None:
                numbers.append(int(match.group(1)))
    patches_dir = _proposals_patches_dir(root)
    if patches_dir.exists():
        for path in patches_dir.iterdir():
            if path.is_file() and path.suffix == ".json":
                match = _PROPOSAL_PATTERN.fullmatch(path.stem)
                if match is not None:
                    numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _next_version_number(root: Path) -> int:
    numbers = []
    versions_dir = _versions_dir(root)
    if versions_dir.exists():
        for path in versions_dir.iterdir():
            if path.is_dir() and _VERSION_PATTERN.fullmatch(path.name):
                try:
                    numbers.append(int(path.name[1:]))
                except ValueError:
                    pass
    return max(numbers, default=0) + 1


def _load_manifest(root: Path, version: str) -> dict:
    return read_json(_manifest_path(root, version))


def _object_type_for_id(object_id: str) -> str:
    match = _OBJECT_ID_PATTERN.fullmatch(object_id)
    if match is None:
        raise ValueError(f"invalid object_id: {object_id}")
    prefix = match.group(1)
    for object_type, candidate in ID_PREFIXES.items():
        if candidate == prefix:
            return object_type
    raise ValueError(f"unknown object_id prefix: {prefix}")


def _revision_exists(root: Path, object_id: str, revision: str) -> bool:
    object_type = _object_type_for_id(object_id)
    log_path = Path(root) / "store" / "objects" / f"{object_type}.jsonl"
    if log_path.exists():
        for record in read_jsonl(log_path):
            if record.get("object_id") == object_id and record.get("revision") == revision:
                return True

    if object_type == "relation":
        relation_log = Path(root) / "store" / "relations.jsonl"
        for record in read_jsonl(relation_log):
            if record.get("relation_id") == object_id and record.get("revision") == revision:
                return True

    return False


def _load_version_index(root: Path) -> dict:
    path = _version_index_path(root)
    if not path.exists():
        return {"versions": {}}
    data = read_json(path)
    versions = data.get("versions")
    if not isinstance(versions, dict):
        raise ValueError("invalid versions index")
    return data


def _write_version_index(root: Path, data: dict) -> None:
    write_json_atomic(_version_index_path(root), data)


def _version_relative_prefix(relative_path: str) -> str | None:
    normalized = relative_path.replace("\\", "/")
    parts = normalized.split("/")
    if len(parts) >= 2 and parts[0] == "versions" and _VERSION_PATTERN.fullmatch(parts[1]):
        return parts[1]
    return None


def _record_version_in_index(root: Path, version: str) -> None:
    data = _load_version_index(root)
    versions = data.setdefault("versions", {})
    manifest_relative = f"versions/{version}/manifest.json"
    entry = versions.get(version)
    if not isinstance(entry, dict):
        entry = {"version": version, "status": "immutable", "files": {}}
        versions[version] = entry
    entry.setdefault("version", version)
    entry["status"] = entry.get("status", "immutable")
    files = entry.setdefault("files", {})
    if not isinstance(files, dict):
        files = {}
        entry["files"] = files
    files.setdefault(
        manifest_relative,
        {"status": "immutable", "reason": None},
    )
    _write_version_index(root, data)


def snapshot_working(root: Path, label: str) -> dict:
    """Capture the current working object revisions as a proposal snapshot."""
    root = Path(root)
    label = _require_nonempty_string(label, "label")

    project = _load_project(root)
    parent = project.get("active_version")
    if parent is not None:
        if not isinstance(parent, str) or _VERSION_PATTERN.fullmatch(parent) is None:
            raise ValueError(f"invalid active_version in project: {parent}")
        if not _manifest_path(root, parent).is_file():
            raise ValueError(f"active version manifest is missing: {parent}")

    objects = _active_object_revisions(root)
    parent_objects = _load_manifest(root, parent).get("objects", {}) if parent else {}
    if not isinstance(parent_objects, dict):
        raise ValueError("invalid parent manifest objects")

    removed = sorted(object_id for object_id in parent_objects if object_id not in objects)
    patch = {
        "objects": {
            object_id: revision
            for object_id, revision in objects.items()
            if parent_objects.get(object_id) != revision
        },
        "removed": removed,
    }

    snapshot_id = f"PRP-{_next_proposal_number(root):04d}"
    record = {
        "snapshot_id": snapshot_id,
        "label": label,
        "created_at": _now(),
        "parent": parent,
        "objects": objects,
        "removed": removed,
        "stale": [],
        "source_versions": _load_source_versions(root),
        "patch": patch,
    }

    append_jsonl(_proposals_index(root), record)
    write_json_atomic(_proposal_patch_path(root, snapshot_id), record)
    return copy.deepcopy(record)


def confirm_batch(
    root: Path,
    batch_id: str,
    decision_ids: list[str],
    object_revisions: dict[str, str],
) -> str:
    """Create an immutable version manifest from confirmed decisions.

    The manifest contains only narrative objects referenced by the confirmed
    batch.  The first version uses the current active revision for each
    referenced object.  Later versions inherit their parent manifest, update
    only batch-referenced active objects to their current revision, and drop
    tombstoned or merged objects.  ``object_revisions`` is an optional caller
    guard: every entry must be referenced by the batch and must match the
    current active revision.
    """
    root = Path(root)
    batch_id = _require_nonempty_string(batch_id, "batch_id")
    decision_ids = _require_string_list(decision_ids, "decision_ids")
    if not decision_ids:
        raise ValueError("decision_ids must not be empty")
    object_revisions = _require_string_mapping(object_revisions, "object_revisions")

    decisions = _load_decisions_index(root)
    referenced_ids: set[str] = set()
    for decision_id in decision_ids:
        decision = decisions.get(decision_id)
        if decision is None:
            raise ValueError(f"unknown decision_id: {decision_id}")
        if decision.get("status") != "confirmed":
            raise ValueError(f"decision is not confirmed: {decision_id}")
        for field in ("affected_objects", "canon_items"):
            values = decision.get(field, [])
            if isinstance(values, list):
                for referenced_id in values:
                    if isinstance(referenced_id, str) and referenced_id.strip():
                        referenced_ids.add(referenced_id)

    version = f"v{_next_version_number(root):03d}"
    manifest_path = _manifest_path(root, version)
    if manifest_path.exists():
        raise FileExistsError(f"version manifest already exists: {manifest_path}")

    active_revisions = _active_object_revisions(root)
    for object_id, revision in object_revisions.items():
        if not isinstance(object_id, str) or not object_id.strip():
            raise ValueError("object_revisions contains an empty object_id")
        if object_id not in referenced_ids:
            raise ValueError(
                f"object is not referenced by the confirmed batch: {object_id}"
            )
        if object_id not in active_revisions:
            raise ValueError(f"object is not active: {object_id}")
        if revision != active_revisions[object_id]:
            raise ValueError(
                f"revision does not match current active revision for {object_id}: {revision}"
            )

    project = _load_project(root)
    parent = project.get("active_version")
    parent_objects = {}
    if parent is not None:
        if not isinstance(parent, str) or _VERSION_PATTERN.fullmatch(parent) is None:
            raise ValueError(f"invalid active_version in project: {parent}")
        parent_manifest = _load_manifest(root, parent)
        parent_objects = parent_manifest.get("objects", {})
        if not isinstance(parent_objects, dict):
            raise ValueError("invalid parent manifest objects")

    if parent is None:
        objects = {
            object_id: active_revisions[object_id]
            for object_id in referenced_ids
            if object_id in active_revisions
        }
    else:
        objects = {
            object_id: revision
            for object_id, revision in parent_objects.items()
            if object_id in active_revisions
        }
        for object_id in referenced_ids:
            if object_id in active_revisions:
                objects[object_id] = active_revisions[object_id]

    for object_id, revision in objects.items():
        if not isinstance(object_id, str) or not object_id.strip():
            raise ValueError("manifest contains an empty object_id")
        if not isinstance(revision, str) or _REVISION_PATTERN.fullmatch(revision) is None:
            raise ValueError(f"invalid revision for {object_id}: {revision}")
        if not _revision_exists(root, object_id, revision):
            raise ValueError(
                f"revision does not exist for {object_id}: {revision}"
            )

    removed = sorted(object_id for object_id in parent_objects if object_id not in objects)
    stale = []

    manifest = {
        "version": version,
        "parent": parent,
        "created_at": _now(),
        "confirmed_batch": batch_id,
        "objects": objects,
        "removed": removed,
        "stale": stale,
        "source_versions": _load_source_versions(root),
        "status": "immutable",
    }
    write_json_atomic(manifest_path, manifest)

    project["active_version"] = version
    _write_project(root, project)
    _record_version_in_index(root, version)
    for object_id in referenced_ids:
        if object_id in objects:
            set_object_confirmed(root, object_id, version)
    return version


def get_status(root: Path) -> dict:
    """Return a small current-state summary for the project."""
    root = Path(root)
    project = _load_project(root)
    active_version = project.get("active_version")
    index = _load_version_index(root)
    indexed_versions = index.get("versions", {})
    if not isinstance(indexed_versions, dict):
        raise ValueError("invalid versions index")

    versions = {}
    versions_dir = _versions_dir(root)
    if versions_dir.exists():
        for path in sorted(versions_dir.iterdir(), key=lambda item: item.name):
            if not path.is_dir() or _VERSION_PATTERN.fullmatch(path.name) is None:
                continue
            version = path.name
            entry = indexed_versions.get(version)
            status = "immutable"
            files = {}
            if isinstance(entry, dict):
                status = entry.get("status", status)
                entry_files = entry.get("files")
                if isinstance(entry_files, dict):
                    files = copy.deepcopy(entry_files)
            versions[version] = {
                "version": version,
                "path": f"versions/{version}",
                "status": status,
                "files": files,
            }

    proposals = _read_proposals(root)
    top_level_files = index.get("files")
    if not isinstance(top_level_files, dict):
        top_level_files = {}
    return {
        "active_version": active_version,
        "version_count": len(versions),
        "versions": versions,
        "files": copy.deepcopy(top_level_files),
        "proposal_count": len(proposals),
        "working_objects": len(_active_object_revisions(root)),
    }


def mark_tampered(root: Path, relative_path: str, reason: str) -> dict:
    """Mark a file status as tampered without attempting to repair it."""
    root = Path(root)
    relative_path = _require_nonempty_string(relative_path, "relative_path")
    reason = _require_nonempty_string(reason, "reason")
    normalized = relative_path.replace("\\", "/")

    data = _load_version_index(root)
    versions = data.setdefault("versions", {})
    if not isinstance(versions, dict):
        raise ValueError("invalid versions index")

    version = _version_relative_prefix(normalized)
    if version is None:
        version = None
        files = data.setdefault("files", {})
        if not isinstance(files, dict):
            files = {}
            data["files"] = files
        files[normalized] = {"status": "tampered", "reason": reason}
    else:
        entry = versions.get(version)
        if not isinstance(entry, dict):
            entry = {"version": version, "status": "immutable", "files": {}}
            versions[version] = entry
        entry["status"] = "tampered"
        files = entry.setdefault("files", {})
        if not isinstance(files, dict):
            files = {}
            entry["files"] = files
        files[normalized] = {"status": "tampered", "reason": reason}

    _write_version_index(root, data)
    return {
        "path": normalized,
        "status": "tampered",
        "reason": reason,
        "version": version,
    }


def archive_version(root: Path, version: str) -> dict:
    """Create a zip archive for an existing immutable version manifest."""
    root = Path(root)
    version = _require_nonempty_string(version, "version")
    if _VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError(f"invalid version: {version}")

    manifest_path = _manifest_path(root, version)
    if not manifest_path.is_file():
        raise ValueError(f"version manifest is missing: {manifest_path}")

    archive_dir = _archive_dir(root)
    archive_dir.mkdir(parents=True, exist_ok=True)
    zip_path = archive_dir / f"{version}.zip"
    if zip_path.exists():
        raise FileExistsError(f"archive already exists: {zip_path}")

    with zipfile.ZipFile(
        zip_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        archive.write(manifest_path, arcname=f"versions/{version}/manifest.json")

        patches_dir = _proposals_patches_dir(root)
        if patches_dir.exists():
            for path in sorted(patches_dir.iterdir()):
                if path.is_file() and path.suffix == ".json":
                    archive.write(path, arcname=f"proposals/patches/{path.name}")

        proposals_index = _proposals_index(root)
        if proposals_index.exists():
            archive.write(proposals_index, arcname="proposals/index.jsonl")

    return {
        "version": version,
        "archive": str(zip_path),
        "archived_files": len(zipfile.ZipFile(zip_path).namelist()),
    }


def restore_version(root: Path, version: str, target: Path | None = None) -> dict:
    """Rebuild JSON files for a version manifest from append-only revisions."""
    root = Path(root)
    version = _require_nonempty_string(version, "version")
    if _VERSION_PATTERN.fullmatch(version) is None:
        raise ValueError(f"invalid version: {version}")

    manifest = _load_manifest(root, version)
    objects = manifest.get("objects", {})
    if not isinstance(objects, dict):
        raise ValueError("invalid manifest objects")

    target_root = Path(target) if target is not None else _working_dir(root) / "restored" / version
    if target_root.exists():
        if target_root.is_file() or any(target_root.iterdir()):
            raise FileExistsError(f"target is not empty: {target_root}")
    target_root.mkdir(parents=True, exist_ok=True)

    restored = 0
    for object_id, revision in objects.items():
        if not isinstance(revision, str):
            raise ValueError(f"invalid revision for {object_id}: {revision}")
        record = None
        object_type = _object_type_for_id(object_id)
        log_path = Path(root) / "store" / "objects" / f"{object_type}.jsonl"
        if log_path.exists():
            for candidate in read_jsonl(log_path):
                if candidate.get("object_id") == object_id and candidate.get("revision") == revision:
                    record = candidate
                    break
        if record is None and object_type == "relation":
            relation_log = Path(root) / "store" / "relations.jsonl"
            for candidate in read_jsonl(relation_log):
                if candidate.get("relation_id") == object_id and candidate.get("revision") == revision:
                    record = candidate
                    break
        if record is None:
            raise ValueError(
                f"revision does not exist for {object_id}: {revision}"
            )
        write_json_atomic(target_root / "objects" / f"{object_id}.json", record)
        restored += 1

    write_json_atomic(target_root / "manifest.json", manifest)
    return {
        "version": version,
        "target": str(target_root),
        "objects_restored": restored,
    }


