"""Master-data management for the four CH-Write list categories.

List JSON files are the master source for derived Markdown views.  Items use
stable IDs and keep a per-item revision history so updates never overwrite the
author's selected level or the previous revision.
"""
from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from pathlib import Path

from .constants import FILE_STATUS_VALUES, LIST_LEVELS
from .io import read_json, write_json_atomic

LIST_CATEGORIES = ("structure", "stages", "genre", "deconstruction")

_SIMPLE_REQUIRED = {
    "structure": ("id", "name", "layer", "narrative_function"),
    "stages": ("id", "name", "object_type", "stage_index", "initial_state"),
    "genre": ("id", "name", "main_genre", "subgenre"),
    "deconstruction": ("id", "name", "object_type", "one_line_definition"),
}

_STANDARD_REQUIRED = {
    "structure": ("mainline", "connections"),
    "stages": ("goal", "end_state", "next_stage"),
    "genre": ("tone", "narrative_form", "novel_weight"),
    "deconstruction": ("core_attributes", "function", "current_state"),
}

_FULL_REQUIRED = (
    "source_refs",
    "status",
    "related_items",
    "impact",
    "conflicts",
    "open_questions",
)

_STRING_ARRAY_FIELDS = (
    "connections",
    "source_refs",
    "related_items",
    "impact",
    "conflicts",
    "open_questions",
)

_REVISION_PATTERN = re.compile(r"^rev-([0-9]+)$")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_nonempty_string(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
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


def _list_path(root: Path, category: str) -> Path:
    return Path(root) / "store" / "lists" / f"{category}.json"


def _next_revision(revision: str | None) -> str:
    match = _REVISION_PATTERN.fullmatch(revision or "")
    number = int(match.group(1)) if match else 0
    return f"rev-{number + 1:04d}"


def validate_list_item(category: str, item: dict, level: str) -> None:
    """Validate one list item before it is written as master data."""
    if category not in LIST_CATEGORIES:
        raise ValueError(f"category must be one of {LIST_CATEGORIES}")
    if level not in LIST_LEVELS:
        raise ValueError(f"level must be one of {LIST_LEVELS}")
    if not isinstance(item, dict):
        raise ValueError("item must be a dict")

    _require_nonempty_string(item.get("id"), "id")
    _require_nonempty_string(item.get("name"), "name")

    if "category" in item:
        _require_nonempty_string(item.get("category"), "category")
        if item["category"] != category:
            raise ValueError("item category must match the category argument")
    if "level" in item:
        _require_nonempty_string(item.get("level"), "level")
        if item["level"] != level:
            raise ValueError("item level must match the level argument")

    for field in _SIMPLE_REQUIRED[category]:
        if field not in item:
            raise ValueError(
                f"list item is missing required field for {level}: {field}"
            )

    for field in _STRING_ARRAY_FIELDS:
        if field in item:
            _require_string_array(item[field], field)

    if "status" in item:
        status = _require_nonempty_string(item.get("status"), "status")
        if status not in FILE_STATUS_VALUES:
            raise ValueError(f"status must be one of {FILE_STATUS_VALUES}")

    if level in ("standard", "full"):
        for field in _STANDARD_REQUIRED[category]:
            if field not in item:
                raise ValueError(
                    f"standard or full list item is missing required field: {field}"
                )

    if level == "full":
        for field in _FULL_REQUIRED:
            if field not in item:
                raise ValueError(f"full list item is missing required field: {field}")


def _load_list(root: Path, category: str) -> dict:
    path = _list_path(root, category)
    if not path.exists():
        return {"category": category, "items": []}

    data = read_json(path)
    items = data.get("items")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ValueError(f"invalid list master data: {path}")
    return data


def upsert_list_item(root: Path, category: str, item: dict, level: str) -> dict:
    """Insert or update one master-data list item.

    The selected ``level`` is authoritative and is written onto the stored
    item.  Updating an item increments its revision and appends the previous
    revision to ``history``; the previous revision is never discarded.
    """
    root = Path(root)
    _require_initialized_project(root)
    validate_list_item(category, item, level)

    data = _load_list(root, category)
    items = data.setdefault("items", [])
    if not isinstance(items, list):
        raise ValueError("invalid list items")

    now = _now()
    incoming = copy.deepcopy(item)
    incoming["category"] = category
    incoming["level"] = level

    for index, existing in enumerate(items):
        if not isinstance(existing, dict):
            continue
        if existing.get("id") == incoming["id"]:
            old = copy.deepcopy(existing)
            old_snapshot = {
                key: copy.deepcopy(value)
                for key, value in old.items()
                if key != "history"
            }
            replacement = copy.deepcopy(incoming)
            replacement["created_at"] = old.get("created_at", now)
            replacement["revision"] = _next_revision(old.get("revision"))
            replacement["history"] = list(old.get("history", [])) + [old_snapshot]
            replacement["updated_at"] = now
            replacement.setdefault("history", [])
            items[index] = replacement
            data["category"] = category
            write_json_atomic(_list_path(root, category), data)
            return copy.deepcopy(replacement)

    new_item = copy.deepcopy(incoming)
    new_item["created_at"] = now
    new_item["updated_at"] = now
    new_item["revision"] = "rev-0001"
    new_item.setdefault("history", [])
    items.append(new_item)
    data["category"] = category
    write_json_atomic(_list_path(root, category), data)
    return copy.deepcopy(new_item)
