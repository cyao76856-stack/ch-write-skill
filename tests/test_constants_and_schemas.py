import json
import unittest
from pathlib import Path

from ch_write import constants

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "assets" / "schemas"


class TestConstantsAndSchemas(unittest.TestCase):
    def test_required_enums_match_frozen_values(self):
        self.assertEqual(constants.ID_PREFIXES, {
            "character": "CHR", "location": "LOC", "faction": "FCT",
            "event": "EVT", "item": "OBJ", "rule": "RUL",
            "relation": "REL", "theme": "THM", "scene": "SCN",
            "stage": "STG", "structure": "STR", "decision": "DEC",
            "change": "CHG", "source": "SRC",
        })
        self.assertEqual(
            constants.PROVENANCE_VALUES,
            ("source-derived", "inferred", "proposed", "imported", "unknown"),
        )
        self.assertEqual(
            constants.DECISION_STATUS_VALUES,
            ("pending", "confirmed", "rejected", "withdrawn", "superseded", "stale", "waived"),
        )
        self.assertEqual(
            constants.FILE_STATUS_VALUES,
            ("draft", "reviewed", "confirmed", "immutable", "tampered"),
        )
        self.assertEqual(
            constants.CANON_MEMBERSHIP_VALUES,
            ("active", "stale", "excluded"),
        )
        self.assertEqual(constants.INTERACTION_PROFILES, ("deep", "balanced", "fast"))
        self.assertEqual(constants.LIST_LEVELS, ("simple", "standard", "full"))
        self.assertEqual(
            constants.QUESTION_DEPTH_VALUES,
            ("full", "focused", "minimal"),
        )
        self.assertEqual(
            constants.CONFIRMATION_GRANULARITY_VALUES,
            ("individual", "batch", "phase"),
        )
        self.assertEqual(
            constants.VERSION_CADENCE_VALUES,
            ("scene", "act", "batch"),
        )
        self.assertEqual(
            constants.OUTPUT_DETAIL_VALUES,
            ("brief", "standard", "detailed"),
        )

    def test_schemas_are_valid_json_with_required_keys(self):
        expected = {
            "project.schema.json": "properties",
            "object.schema.json": "properties",
            "decision.schema.json": "properties",
            "change.schema.json": "properties",
            "version.schema.json": "properties",
            "list.schema.json": "properties",
        }
        for filename, key in expected.items():
            with self.subTest(filename=filename):
                data = json.loads((SCHEMAS / filename).read_text("utf-8"))
                self.assertIn(key, data)
                self.assertEqual(data["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertEqual(data["type"], "object")
                for required_key in ("title", "properties", "required"):
                    self.assertIn(required_key, data)

    def test_project_schema_requires_structured_interaction_profile(self):
        project = json.loads((SCHEMAS / "project.schema.json").read_text("utf-8"))
        profile = project["properties"]["interaction_profile"]
        self.assertEqual(profile["type"], "object")
        self.assertEqual(set(profile["required"]), {
            "preset",
            "question_depth",
            "confirmation_granularity",
            "version_cadence",
            "output_detail",
        })
        expected_enums = {
            "preset": constants.INTERACTION_PROFILES,
            "question_depth": constants.QUESTION_DEPTH_VALUES,
            "confirmation_granularity": constants.CONFIRMATION_GRANULARITY_VALUES,
            "version_cadence": constants.VERSION_CADENCE_VALUES,
            "output_detail": constants.OUTPUT_DETAIL_VALUES,
        }
        for field, expected in expected_enums.items():
            with self.subTest(field=field):
                self.assertEqual(
                    profile["properties"][field]["enum"],
                    list(expected),
                )

    def test_decision_schema_requires_author_intent_fields(self):
        data = json.loads((SCHEMAS / "decision.schema.json").read_text("utf-8"))
        required = set(data["required"])
        self.assertTrue({
            "decision_id",
            "content",
            "secondary_reasons",
            "main_reason",
            "direct_purpose",
            "expected_effect",
            "status",
            "author_statement",
        }.issubset(required))
        self.assertEqual(
            data["properties"]["status"]["enum"],
            list(constants.DECISION_STATUS_VALUES),
        )

    def test_object_schema_type_enum_matches_runtime_narrative_types(self):
        obj = json.loads((SCHEMAS / "object.schema.json").read_text("utf-8"))
        self.assertEqual(
            obj["properties"]["type"]["enum"],
            list(constants.NARRATIVE_OBJECT_TYPES),
        )

    def test_schema_enums_use_frozen_values(self):
        obj = json.loads((SCHEMAS / "object.schema.json").read_text("utf-8"))
        listing = json.loads((SCHEMAS / "list.schema.json").read_text("utf-8"))
        self.assertEqual(
            obj["properties"]["provenance"]["enum"],
            list(constants.PROVENANCE_VALUES),
        )
        self.assertEqual(
            listing["properties"]["level"]["enum"],
            list(constants.LIST_LEVELS),
        )


    def test_list_schema_string_arrays_match_runtime(self):
        listing = json.loads((SCHEMAS / "list.schema.json").read_text("utf-8"))
        for field in ("impact", "conflicts", "open_questions"):
            prop = listing["properties"][field]
            self.assertEqual(prop["type"], "array")
            self.assertEqual(prop["items"], {"type": "string"})


if __name__ == "__main__":
    unittest.main()
