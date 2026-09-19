import copy
import re
from datetime import datetime, timezone
from pathlib import Path

from .constants import DECISION_STATUS_VALUES, INTERACTION_PROFILES, PROVENANCE_VALUES
from .io import append_jsonl, read_json, read_jsonl, write_json_atomic
from .project import INTERACTION_PROFILE_PRESETS

_DECISION_ID_PATTERN = re.compile(r"^DEC-[0-9]{4,}$")
_CHANGE_ID_PATTERN = re.compile(r"^CHG-[0-9]{4,}$")
_DECISION_NUMBER_PATTERN = re.compile(r"^DEC-([0-9]+)$")
_CHANGE_NUMBER_PATTERN = re.compile(r"^CHG-([0-9]+)$")

CHANGE_EXECUTION_STATUS_VALUES = (
    "pending", "applied", "verified", "failed", "skipped", "superseded",
)

_DECISION_EVENT_TYPES = (
    "proposed", "confirmed", "rejected", "withdrawn", "superseded", "waived",
    "profile_changed",
)
_EVENT_TYPE_TO_STATUS = {
    "proposed": "pending",
    "confirmed": "confirmed",
    "rejected": "rejected",
    "withdrawn": "withdrawn",
    "superseded": "superseded",
    "waived": "waived",
}

_NEGATIVE_OR_FUZZY_MARKERS = (
    "都可以", "随便", "你决定", "先这样", "应该没问题",
    "不行", "不可以", "不同意", "不接受", "不确认",
    "拒绝接受", "未接受", "拒绝确认", "未确认", "拒绝同意", "未同意",
)
_STANDALONE_YES_WORDS = ("确认", "可以", "行", "同意")
_EXPLICIT_ID_VERBS = ("接受", "确认", "同意")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _decisions_log(root: Path) -> Path:
    return Path(root) / "logs" / "decisions.jsonl"


def _changes_log(root: Path) -> Path:
    return Path(root) / "logs" / "changes.jsonl"


def _decisions_index(root: Path) -> Path:
    return Path(root) / "indexes" / "decisions.json"


def _require_nonempty_string(value, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _require_string_list(value, label: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be a list of strings")
    return list(value)


def _require_string_or_none(value, label: str) -> str | None:
    if value is not None and not isinstance(value, str):
        raise ValueError(f"{label} must be a string or null")
    return value


def _validate_decision_id(decision_id: str) -> None:
    if not isinstance(decision_id, str) or _DECISION_ID_PATTERN.fullmatch(decision_id) is None:
        raise ValueError(f"invalid decision_id: {decision_id}")


def _validate_change_id(change_id: str) -> None:
    if not isinstance(change_id, str) or _CHANGE_ID_PATTERN.fullmatch(change_id) is None:
        raise ValueError(f"invalid change_id: {change_id}")


def _read_decision_events(root: Path) -> list[dict]:
    return read_jsonl(_decisions_log(root))


def _build_decisions_index(events: list[dict]) -> dict:
    decisions = {}
    for event in events:
        decision_id = event.get("decision_id")
        event_type = event.get("event_type")
        if not isinstance(decision_id, str) or event_type not in _EVENT_TYPE_TO_STATUS:
            continue
        record = copy.deepcopy(event)
        record["status"] = _EVENT_TYPE_TO_STATUS[event_type]
        decisions[decision_id] = record
    return decisions


def _write_decisions_index(root: Path, decisions: dict) -> None:
    write_json_atomic(_decisions_index(root), {"decisions": decisions})


def _rebuild_decisions_index(root: Path) -> dict:
    decisions = _build_decisions_index(_read_decision_events(root))
    _write_decisions_index(root, decisions)
    return decisions


def _load_decisions_index(root: Path) -> dict:
    path = _decisions_index(root)
    if path.exists():
        data = read_json(path)
        decisions = data.get("decisions")
        if not isinstance(decisions, dict):
            raise ValueError("invalid decisions index")
        return decisions
    return _rebuild_decisions_index(root)


def _next_decision_number(root: Path) -> int:
    numbers = []
    for decision_id in _load_decisions_index(root):
        if isinstance(decision_id, str):
            match = _DECISION_NUMBER_PATTERN.fullmatch(decision_id)
            if match is not None:
                numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def _next_change_number(root: Path) -> int:
    numbers = []
    for record in read_jsonl(_changes_log(root)):
        value = record.get("change_id")
        if isinstance(value, str):
            match = _CHANGE_NUMBER_PATTERN.fullmatch(value)
            if match is not None:
                numbers.append(int(match.group(1)))
    return max(numbers, default=0) + 1


def record_decision(root: Path, payload: dict) -> dict:
    root = Path(root)
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")

    title = _require_nonempty_string(payload.get("title"), "title")
    content = _require_nonempty_string(payload.get("content"), "content")
    main_reason = _require_nonempty_string(payload.get("main_reason"), "main_reason")
    direct_purpose = _require_nonempty_string(payload.get("direct_purpose"), "direct_purpose")
    expected_effect = _require_nonempty_string(payload.get("expected_effect"), "expected_effect")
    decision_type = payload.get("type", "decision")
    if not isinstance(decision_type, str):
        raise ValueError("type must be a string")

    decision_id = payload.get("decision_id")
    if decision_id is None:
        decision_id = f"DEC-{_next_decision_number(root):04d}"
    _validate_decision_id(decision_id)
    for existing_id in _load_decisions_index(root):
        if existing_id == decision_id:
            raise ValueError(f"duplicate decision_id: {decision_id}")

    alternatives = payload.get("alternatives", [])
    if not isinstance(alternatives, list):
        raise ValueError("alternatives must be a list")
    for alternative in alternatives:
        if not isinstance(alternative, dict):
            raise ValueError("alternatives must be a list of objects")
        if not isinstance(alternative.get("text"), str):
            raise ValueError("each alternative must include a text string")
        if not isinstance(alternative.get("rejected_reason"), str):
            raise ValueError("each alternative must include a rejected_reason string")

    now = _now()
    record = {
        "event_type": "proposed",
        "decision_id": decision_id,
        "title": title,
        "type": decision_type,
        "content": content,
        "main_reason": main_reason,
        "secondary_reasons": _require_string_list(
            payload.get("secondary_reasons", []), "secondary_reasons"
        ),
        "direct_purpose": direct_purpose,
        "expected_effect": expected_effect,
        "alternatives": alternatives,
        "rejection_reasons": _require_string_list(
            payload.get("rejection_reasons", []), "rejection_reasons"
        ),
        "dependencies": _require_string_list(
            payload.get("dependencies", []), "dependencies"
        ),
        "affected_objects": _require_string_list(
            payload.get("affected_objects", []), "affected_objects"
        ),
        "canon_items": _require_string_list(
            payload.get("canon_items", []), "canon_items"
        ),
        "author_statement": "",
        "status": "pending",
        "provenance": payload.get("provenance", "proposed"),
        "version": None,
        "supersedes": None,
        "superseded_by": None,
        "batch_id": payload.get("batch_id"),
        "confirmed_at": None,
        "created_at": now,
        "updated_at": now,
    }

    if record["provenance"] not in PROVENANCE_VALUES:
        raise ValueError(f"provenance must be one of {PROVENANCE_VALUES}")

    append_jsonl(_decisions_log(root), record)
    _rebuild_decisions_index(root)
    return copy.deepcopy(record)


def confirm_decision(
    root: Path,
    decision_id: str,
    author_statement: str,
    batch_id: str | None = None,
) -> dict:
    root = Path(root)
    _validate_decision_id(decision_id)
    author_statement = _require_nonempty_string(author_statement, "author_statement")
    if not is_explicit_confirmation(author_statement, [decision_id]):
        raise ValueError("author_statement is not an explicit confirmation")

    current = _load_decisions_index(root).get(decision_id)
    if current is None:
        raise ValueError(f"unknown decision_id: {decision_id}")
    if current.get("status") != "pending":
        raise ValueError(f"decision is not pending: {decision_id}")

    updated = copy.deepcopy(current)
    updated["event_type"] = "confirmed"
    updated["status"] = "confirmed"
    updated["author_statement"] = author_statement
    if batch_id is not None:
        updated["batch_id"] = batch_id
    now = _now()
    updated["confirmed_at"] = now
    updated["updated_at"] = now

    append_jsonl(_decisions_log(root), updated)
    _rebuild_decisions_index(root)
    return copy.deepcopy(updated)


def record_change(root: Path, payload: dict) -> dict:
    root = Path(root)
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")

    change_type = _require_nonempty_string(payload.get("type"), "type")
    location = _require_nonempty_string(payload.get("location"), "location")
    original = _require_nonempty_string(payload.get("original"), "original")
    problem = _require_nonempty_string(payload.get("problem"), "problem")
    proposal = _require_nonempty_string(payload.get("proposal"), "proposal")
    expected_effect = _require_nonempty_string(payload.get("expected_effect"), "expected_effect")
    if "impact" not in payload:
        raise ValueError("impact is required")
    impact = payload["impact"]

    related_objects = _require_string_list(
        payload.get("related_objects", []), "related_objects"
    )
    followups = _require_string_list(payload.get("followups", []), "followups")

    confirmation_status = payload.get("confirmation_status", "pending")
    if confirmation_status not in DECISION_STATUS_VALUES:
        raise ValueError(f"confirmation_status must be one of {DECISION_STATUS_VALUES}")

    execution_status = payload.get("execution_status", "pending")
    if execution_status not in CHANGE_EXECUTION_STATUS_VALUES:
        raise ValueError(f"execution_status must be one of {CHANGE_EXECUTION_STATUS_VALUES}")

    provenance = payload.get("provenance", "proposed")
    if provenance not in PROVENANCE_VALUES:
        raise ValueError(f"provenance must be one of {PROVENANCE_VALUES}")

    author_statement = payload.get("author_statement", "")
    if not isinstance(author_statement, str):
        raise ValueError("author_statement must be a string")

    version = _require_string_or_none(payload.get("version"), "version")

    change_id = payload.get("change_id")
    if change_id is None:
        change_id = f"CHG-{_next_change_number(root):04d}"
    _validate_change_id(change_id)
    for existing in read_jsonl(_changes_log(root)):
        if existing.get("change_id") == change_id:
            raise ValueError(f"duplicate change_id: {change_id}")

    now = _now()
    record = {
        "change_id": change_id,
        "type": change_type,
        "location": location,
        "original": original,
        "problem": problem,
        "proposal": proposal,
        "expected_effect": expected_effect,
        "related_objects": related_objects,
        "impact": impact,
        "confirmation_status": confirmation_status,
        "execution_status": execution_status,
        "followups": followups,
        "provenance": provenance,
        "author_statement": author_statement,
        "version": version,
        "created_at": now,
        "updated_at": now,
    }
    append_jsonl(_changes_log(root), record)
    return copy.deepcopy(record)


def is_explicit_confirmation(text: str, pending_ids: list[str]) -> bool:
    if not isinstance(text, str):
        return False
    text = text.strip()
    if not text:
        return False

    for marker in _NEGATIVE_OR_FUZZY_MARKERS:
        if marker in text:
            return False

    pending_ids = list(pending_ids or [])
    decision_ids = re.findall(r"DEC-[0-9]{4,}", text)
    if decision_ids:
        if len(decision_ids) != 1 or decision_ids[0] not in pending_ids:
            return False
        verb_pattern = "|".join(_EXPLICIT_ID_VERBS)
        accepted_pattern = re.compile(
            rf"^(?:(?:好的|好|嗯)[\s，,。！!？?]*)?(?:{verb_pattern})\s*DEC-[0-9]{{4,}}[\s，,。！!？?]*$"
        )
        if accepted_pattern.fullmatch(text) is None:
            return False
        return True

    if len(pending_ids) == 1:
        stripped = text.strip().strip("。！!？?，, ")
        if stripped in _STANDALONE_YES_WORDS:
            return True

    return False


def set_interaction_profile(
    root: Path,
    profile: str,
    author_statement: str,
) -> dict:
    root = Path(root)
    if profile not in INTERACTION_PROFILES:
        raise ValueError(f"profile must be one of {INTERACTION_PROFILES}")
    author_statement = _require_nonempty_string(author_statement, "author_statement")

    project_path = root / "project.json"
    project = read_json(project_path)
    old_profile = copy.deepcopy(project.get("interaction_profile"))
    new_profile = copy.deepcopy(INTERACTION_PROFILE_PRESETS[profile])
    project["interaction_profile"] = new_profile
    write_json_atomic(project_path, project)

    effective_at = _now()
    entry = {
        "event_type": "profile_changed",
        "author_statement": author_statement,
        "old_interaction_profile": old_profile,
        "new_interaction_profile": new_profile,
        "effective_at": effective_at,
    }
    append_jsonl(_decisions_log(root), entry)

    return {
        "interaction_profile": profile,
        "old_interaction_profile": old_profile,
        "new_interaction_profile": new_profile,
        "author_statement": author_statement,
        "effective_at": effective_at,
    }
