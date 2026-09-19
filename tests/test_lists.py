import tempfile
import unittest
from pathlib import Path

from ch_write.project import init_project
from ch_write.lists import upsert_list_item, validate_list_item


def _simple_structure_item():
    return {
        "id": "STR-0001",
        "name": "开场",
        "layer": "act",
        "narrative_function": "建立危机",
    }


def _full_structure_item():
    return {
        "id": "STR-0001",
        "name": "开场",
        "layer": "act",
        "narrative_function": "建立危机",
        "mainline": True,
        "start_state": "稳定",
        "conflict": "异变",
        "choice": "调查",
        "turn": "发现尸体",
        "result": "局势升级",
        "cause": "商船滞留",
        "information_change": "读者获知阴谋",
        "setup_payoff": "尸体对应爆炸",
        "connections": ["EVT-0001"],
        "related_items": ["EVT-0002"],
        "impact": ["FCT-0001"],
        "source_refs": ["SRC-0001"],
        "conflicts": ["内外矛盾"],
        "open_questions": ["凶手动机"],
        "status": "confirmed",
    }


class TestLists(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "story"
        init_project(self.root, "Story", "markdown", "balanced")

    def tearDown(self):
        self.tmp.cleanup()

    def test_simple_requires_core_fields(self):
        with self.assertRaises(ValueError):
            validate_list_item("structure", {"id": "STR-0001"}, "simple")
        validate_list_item("structure", _simple_structure_item(), "simple")

    def test_update_appends_revision_history(self):
        first = upsert_list_item(self.root, "structure", _simple_structure_item(), "simple")
        updated_item = dict(_simple_structure_item(), name="开场-修订")
        second = upsert_list_item(self.root, "structure", updated_item, "simple")
        self.assertEqual(first["revision"], "rev-0001")
        self.assertEqual(second["revision"], "rev-0002")
        self.assertEqual(len(second["history"]), 1)
        self.assertEqual(second["history"][0]["name"], "开场")
        self.assertEqual(second["history"][0]["revision"], "rev-0001")

    def test_high_weight_cannot_downgrade_selected_level(self):
        result = upsert_list_item(self.root, "structure", _full_structure_item(), "full")
        self.assertEqual(result["level"], "full")
        self.assertEqual(result["history"], [])
        self.assertTrue((self.root / "store" / "lists" / "structure.json").exists())

    def test_full_requires_gap_fields(self):
        item = _full_structure_item()
        for field in ("related_items", "conflicts", "open_questions"):
            with self.subTest(field=field):
                bad = dict(item)
                bad.pop(field)
                with self.assertRaises(ValueError):
                    validate_list_item("structure", bad, "full")

    def test_type_failures_are_rejected(self):
        with self.assertRaises(ValueError):
            validate_list_item("structure", dict(_simple_structure_item(), id=123), "simple")
        with self.assertRaises(ValueError):
            validate_list_item("structure", dict(_simple_structure_item(), name=None), "simple")
        with self.assertRaises(ValueError):
            validate_list_item("structure", dict(_simple_structure_item(), status="pending"), "simple")
        with self.assertRaises(ValueError):
            validate_list_item(
                "structure",
                dict(_simple_structure_item(), connections=["EVT-0001", 123]),
                "simple",
            )

    def test_uninitialized_project_rejected(self):
        missing = Path(self.tmp.name) / "missing"
        with self.assertRaises(FileNotFoundError):
            upsert_list_item(missing, "structure", _simple_structure_item(), "simple")


if __name__ == "__main__":
    unittest.main()
