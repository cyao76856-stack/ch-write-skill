ID_PREFIXES = {
    "character": "CHR", "location": "LOC", "faction": "FCT",
    "event": "EVT", "item": "OBJ", "rule": "RUL",
    "relation": "REL", "theme": "THM", "scene": "SCN",
    "stage": "STG", "structure": "STR", "decision": "DEC",
    "change": "CHG", "source": "SRC",
}
NARRATIVE_OBJECT_TYPES = (
    "character", "location", "faction", "event", "item", "rule",
    "theme", "scene", "stage", "structure",
)

PROVENANCE_VALUES = ("source-derived", "inferred", "proposed", "imported", "unknown")
DECISION_STATUS_VALUES = ("pending", "confirmed", "rejected", "withdrawn", "superseded", "stale", "waived")
FILE_STATUS_VALUES = ("draft", "reviewed", "confirmed", "immutable", "tampered")
CANON_MEMBERSHIP_VALUES = ("active", "stale", "excluded")
INTERACTION_PROFILES = ("deep", "balanced", "fast")
QUESTION_DEPTH_VALUES = ("full", "focused", "minimal")
CONFIRMATION_GRANULARITY_VALUES = ("individual", "batch", "phase")
VERSION_CADENCE_VALUES = ("scene", "act", "batch")
OUTPUT_DETAIL_VALUES = ("brief", "standard", "detailed")
LIST_LEVELS = ("simple", "standard", "full")