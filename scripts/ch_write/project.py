from datetime import datetime, timezone
from pathlib import Path

from .constants import INTERACTION_PROFILES
from .io import read_json, write_json_atomic

SCRIPT_MASTERS = ("markdown", "fountain")
PROJECT_DIRECTORIES = (
    "indexes",
    "store/objects",
    "store/lists",
    "store/blobs",
    "logs",
    "versions",
    "working",
    "proposals/patches",
    "views",
    "exports",
    "archive",
)
INTERACTION_PROFILE_PRESETS = {
    "deep": {
        "preset": "deep",
        "question_depth": "full",
        "confirmation_granularity": "individual",
        "version_cadence": "scene",
        "output_detail": "detailed",
    },
    "balanced": {
        "preset": "balanced",
        "question_depth": "focused",
        "confirmation_granularity": "batch",
        "version_cadence": "act",
        "output_detail": "standard",
    },
    "fast": {
        "preset": "fast",
        "question_depth": "minimal",
        "confirmation_granularity": "batch",
        "version_cadence": "batch",
        "output_detail": "brief",
    },
}


def init_project(
    root: Path,
    name: str,
    script_master: str,
    interaction_profile: str,
) -> Path:
    root = Path(root)
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Project name must be a non-empty string")
    if script_master not in SCRIPT_MASTERS:
        raise ValueError(f"script_master must be one of {SCRIPT_MASTERS}")
    if interaction_profile not in INTERACTION_PROFILES:
        raise ValueError(
            f"interaction_profile must be one of {INTERACTION_PROFILES}"
        )

    project_file = root / "project.json"
    if project_file.exists():
        raise FileExistsError(f"Project already initialized: {project_file}")

    root.mkdir(parents=True, exist_ok=True)
    for relative_path in PROJECT_DIRECTORIES:
        (root / relative_path).mkdir(parents=True, exist_ok=True)

    metadata = {
        "schema_version": 1,
        "name": name,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "master_formats": {"lists": "json", "script": script_master},
        "interaction_profile": dict(INTERACTION_PROFILE_PRESETS[interaction_profile]),
        "active_version": None,
    }
    write_json_atomic(project_file, metadata)
    return root


def load_project(root: Path) -> dict:
    return read_json(Path(root) / "project.json")
