from datetime import datetime, timezone
from pathlib import Path
import hashlib
import re

from .docx import extract_docx_text
from .io import read_json, write_json_atomic


_SOURCE_ID_PATTERN = re.compile(r"^SRC-([0-9]+)$")
_SOURCE_INDEX = Path("indexes") / "sources.json"


def compute_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _normalized_path(path) -> str:
    return str(Path(path).expanduser().resolve(strict=False))


def _load_sources(root: Path) -> list[dict]:
    index_path = Path(root) / _SOURCE_INDEX
    if not index_path.exists():
        return []
    data = read_json(index_path)
    sources = data.get("sources")
    if not isinstance(sources, list) or not all(
        isinstance(source, dict) for source in sources
    ):
        raise ValueError("invalid sources index")
    return [dict(source) for source in sources]


def _validate_sources(sources: list[dict]) -> None:
    source_ids = set()
    paths = set()
    for source in sources:
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or _SOURCE_ID_PATTERN.fullmatch(source_id) is None:
            raise ValueError(f"invalid source_id: {source_id}")
        if source_id in source_ids:
            raise ValueError(f"duplicate source_id: {source_id}")
        source_ids.add(source_id)

        path = source.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("source path must be a non-empty string")
        normalized = _normalized_path(path)
        if normalized in paths:
            raise ValueError(f"duplicate source path: {path}")
        paths.add(normalized)


def _next_source_number(sources: list[dict]) -> int:
    numbers = [
        int(_SOURCE_ID_PATTERN.fullmatch(source["source_id"]).group(1))
        for source in sources
    ]
    return max(numbers, default=0) + 1


def _snapshot(path: Path) -> dict:
    path = Path(path)
    if not path.is_file():
        return {
            "size": None,
            "modified_at": None,
            "digest": None,
            "status": "missing",
        }

    stat = path.stat()
    return {
        "size": stat.st_size,
        "modified_at": datetime.fromtimestamp(
            stat.st_mtime, tz=timezone.utc
        ).isoformat(),
        "digest": compute_digest(path),
        "status": "registered",
    }


def _recheck_source(source: dict) -> None:
    previous_digest = source.get("digest")
    snapshot = _snapshot(Path(source["path"]))

    if snapshot["status"] == "missing":
        source["status"] = "missing"
        return

    if previous_digest is None:
        source.update(snapshot)
        return

    if snapshot["digest"] == previous_digest:
        source["status"] = "registered"
        return

    source["status"] = "source-changed"


def _entry_source_id(entry: dict) -> str | None:
    source_id = entry.get("source_id")
    if source_id is None:
        return None
    if not isinstance(source_id, str) or _SOURCE_ID_PATTERN.fullmatch(source_id) is None:
        raise ValueError(f"invalid source_id: {source_id}")
    return source_id


def _new_source(source_id: str, entry: dict) -> dict:
    path = entry.get("path")
    if not isinstance(path, str) or not path:
        raise ValueError("source path must be a non-empty string")
    if "order" not in entry:
        raise ValueError("source order is required")
    if "priority" not in entry:
        raise ValueError("source priority is required")
    if "merge_strategy" not in entry:
        raise ValueError("source merge_strategy is required")

    input_path = path
    absolute_path = _normalized_path(path)
    record = {
        "source_id": source_id,
        "path": absolute_path,
        "input_path": input_path,
        "order": entry["order"],
        "priority": entry["priority"],
        "merge_strategy": entry["merge_strategy"],
    }
    record.update(_snapshot(Path(absolute_path)))
    return record


def get_source_status(root: Path) -> dict:
    """Return current source statuses without modifying the source index."""
    root = Path(root)
    sources = _load_sources(root)
    report = []
    for source in sources:
        current = dict(source)
        previous_digest = current.get("digest")
        snapshot = _snapshot(Path(current["path"]))
        if snapshot["status"] == "missing":
            current["status"] = "missing"
        elif previous_digest is None:
            current.update(snapshot)
        elif snapshot["digest"] == previous_digest:
            current["status"] = "registered"
        else:
            current["status"] = "source-changed"
        report.append(current)
    return {"sources": report}


def register_sources(
    root: Path,
    entries: list[dict],
    replace: bool = False,
) -> dict:
    root = Path(root)
    sources = _load_sources(root)
    _validate_sources(sources)

    if not isinstance(entries, list):
        raise ValueError("entries must be a list")
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("source entries must be objects")

    existing_by_id = {source["source_id"]: source for source in sources}
    existing_by_path = {
        _normalized_path(source["path"]): source for source in sources
    }
    seen_entry_paths = set()

    for entry in entries:
        path = entry.get("path")
        if not isinstance(path, str) or not path:
            raise ValueError("source path must be a non-empty string")
        normalized_path = _normalized_path(path)
        if normalized_path in seen_entry_paths:
            raise ValueError(f"duplicate source path: {path}")
        seen_entry_paths.add(normalized_path)

        source_id = _entry_source_id(entry)
        source = existing_by_id.get(source_id) if source_id is not None else None
        if source_id is not None and source is None:
            raise ValueError(f"unknown source_id: {source_id}")
        if source is None:
            source = existing_by_path.get(normalized_path)
        if source is None:
            source = _new_source(
                f"SRC-{_next_source_number(sources):04d}",
                entry,
            )
            sources.append(source)
            existing_by_id[source["source_id"]] = source
            existing_by_path[normalized_path] = source
            continue

        old_normalized_path = _normalized_path(source["path"])
        if source_id is not None and old_normalized_path != normalized_path:
            if not replace:
                raise ValueError(
                    f"source_id {source_id} is already registered; use replace=True"
                )

        if not replace:
            _recheck_source(source)
            continue

        collision = existing_by_path.get(normalized_path)
        if collision is not None and collision is not source:
            raise ValueError(f"duplicate source path: {path}")

        replacement = _new_source(source["source_id"], entry)
        source.update(replacement)
        existing_by_path.pop(old_normalized_path, None)
        existing_by_path[normalized_path] = source

    for source in sources:
        _recheck_source(source)

    report = {"sources": sources}
    write_json_atomic(root / _SOURCE_INDEX, report)
    return report