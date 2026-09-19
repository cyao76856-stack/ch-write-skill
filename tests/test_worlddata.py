import tempfile
import unittest
from pathlib import Path

from ch_write.project import init_project
from ch_write.worlddata import append_location_state, append_timeline_entry


def _timeline_entry(event_id):
    return {
        "event_id": event_id,
        "time_kind": "relative",
        "relation": "before",
        "anchor": "EVT-0002",
        "precision": "unknown",
        "status": "pending",
        "source_refs": ["SRC-0001"],
        "known_by": ["CHR-0001"],
    }


def _location_state(location_id):
    return {
        "location_id": location_id,
        "valid_from": "760-01-01",
        "valid_to": None,
        "controller": "FCT-0001",
        "status": "正常",
        "precision": "approximate",
        "roads": [],
        "resources": ["OBJ-0001"],
        "events": ["EVT-0001"],
    }


class TestWorldData(unittest.TestCase):
    def test_timeline_and_location_state_are_append_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            entry = append_timeline_entry(root, "EVT-0001", _timeline_entry("EVT-0001"))
            self.assertEqual(entry["event_id"], "EVT-0001")
            state = append_location_state(root, "LOC-0001", _location_state("LOC-0001"))
            self.assertEqual(state["status"], "正常")
            self.assertEqual(len((root / "store" / "timeline.jsonl").read_text("utf-8").splitlines()), 1)
            self.assertEqual(len((root / "store" / "location_states.jsonl").read_text("utf-8").splitlines()), 1)

    def test_timeline_and_location_state_allow_unknown_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            state = append_location_state(root, "LOC-0002", {
                "location_id": "LOC-0002",
                "valid_from": None,
                "valid_to": None,
                "controller": None,
                "status": "未知",
                "precision": "unknown",
                "roads": [],
                "resources": [],
                "events": [],
            })
            self.assertIsNone(state["valid_from"])
            self.assertIsNone(state["valid_to"])
            self.assertEqual(state["status"], "未知")
            entry = append_timeline_entry(root, "EVT-0003", {
                "event_id": "EVT-0003",
                "time_kind": None,
                "relation": "before",
                "anchor": "EVT-0002",
                "precision": None,
                "status": "unplaced",
                "source_refs": [],
                "known_by": [],
            })
            self.assertEqual(entry["status"], "unplaced")

    def test_uninitialized_project_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "missing"
            with self.assertRaises(FileNotFoundError):
                append_timeline_entry(root, "EVT-0001", _timeline_entry("EVT-0001"))
            with self.assertRaises(FileNotFoundError):
                append_location_state(root, "LOC-0001", _location_state("LOC-0001"))

    def test_missing_minimal_fields_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            entry = _timeline_entry("EVT-0001")
            entry.pop("known_by")
            with self.assertRaises(ValueError):
                append_timeline_entry(root, "EVT-0001", entry)
            state = _location_state("LOC-0001")
            state.pop("events")
            with self.assertRaises(ValueError):
                append_location_state(root, "LOC-0001", state)


if __name__ == "__main__":
    unittest.main()
