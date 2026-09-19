"""Append-only timeline and location-state master data for CH-Write projects.

Timeline entries and location states are append-only JSONL logs.  They never
overwrite history: every new state or time observation is appended as its own
record so conflicting sources and fuzzy dates remain visible.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone
from pathlib import Path

from .io import append_jsonl

_TIMELINE_REQUIRED = (
    "event_id",
    "time_kind",
    "precision",
    "status",
    "source_refs",
    "known_by",
)

_LOCATION_REQUIRED = (
    "location_id",
    "valid_from",
    "valid_to",
    "controller",
    "status",
    "precision",
    "roads",
    "resources",
    "events",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_nonempty_string(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_string_or_none(value, label: str) -> str | None:
    if value is not None:
        _require_nonempty_string(value, label)
    return value


def _require_string_array(value, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    return list(value)


def _project_file(root: Path) -> Path:
    return Path(root) / "project.json"


def _require_initialized_project(root: Path) -> None:
    if not _project_file(root).is_file():
        raise FileNotFoundError(f"project is not initialized: {_project_file(root)}")


def _timeline_path(root: Path) -> Path:
    return Path(root) / "store" / "timeline.jsonl"


def _location_states_path(root: Path) -> Path:
    return Path(root) / "store" / "location_states.jsonl"


def append_timeline_entry(root: Path, event_id: str, entry: dict) -> dict:
    """Append one timeline observation for ``event_id``."""
    root = Path(root)
    _require_initialized_project(root)
    event_id = _require_nonempty_string(event_id, "event_id")
    if not isinstance(entry, dict):
        raise ValueError("entry must be a dict")

    record = copy.deepcopy(entry)
    if record.get("event_id") != event_id:
        raise ValueError("entry event_id must match the event_id argument")
    for field in _TIMELINE_REQUIRED:
        if field not in record:
            raise ValueError(f"timeline entry is missing required field: {field}")

    _require_nonempty_string(record.get("event_id"), "event_id")
    for field in ("time_kind", "precision", "status"):
        _require_string_or_none(record.get(field), field)
    for field in ("source_refs", "known_by"):
        _require_string_array(record.get(field), field)
    record["appended_at"] = _now()

    append_jsonl(_timeline_path(root), record)
    return copy.deepcopy(record)


def append_location_state(root: Path, location_id: str, state: dict) -> dict:
    """Append one location-state observation for ``location_id``."""
    root = Path(root)
    _require_initialized_project(root)
    location_id = _require_nonempty_string(location_id, "location_id")
    if not isinstance(state, dict):
        raise ValueError("state must be a dict")

    record = copy.deepcopy(state)
    if record.get("location_id") != location_id:
        raise ValueError("state location_id must match the location_id argument")
    for field in _LOCATION_REQUIRED:
        if field not in record:
            raise ValueError(f"location state is missing required field: {field}")

    _require_nonempty_string(record.get("location_id"), "location_id")
    for field in ("valid_from", "valid_to", "controller"):
        _require_string_or_none(record.get(field), field)
    for field in ("status", "precision"):
        _require_nonempty_string(record.get(field), field)
    for field in ("roads", "resources", "events"):
        _require_string_array(record.get(field), field)
    record["appended_at"] = _now()

    append_jsonl(_location_states_path(root), record)
    return copy.deepcopy(record)
