import tempfile
import unittest
from pathlib import Path
from ch_write.project import init_project
from ch_write.decisions import (
    confirm_decision, is_explicit_confirmation, record_change, record_decision
)

class TestDecisions(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "story"
        init_project(self.root, "Story", "markdown", "balanced")

    def test_proposal_and_confirmation_are_append_only_events_with_current_index(self):
        from ch_write.io import read_json, read_jsonl
        decision = record_decision(self.root, {
            "title": "主角背叛",
            "content": "主角背叛朋友",
            "main_reason": "让忠诚主题产生代价",
            "direct_purpose": "把人物推进不可逆选择",
            "expected_effect": "读者看到关系的破裂",
            "alternatives": [{"text": "不背叛", "rejected_reason": "冲突会消失"}],
            "affected_objects": ["CHR-0001"],
        })
        confirm_decision(self.root, decision["decision_id"], "接受 " + decision["decision_id"])
        events = read_jsonl(self.root / "logs" / "decisions.jsonl")
        self.assertEqual([event["event_type"] for event in events], ["proposed", "confirmed"])
        self.assertEqual(events[0]["decision_id"], decision["decision_id"])
        self.assertEqual(events[1]["status"], "confirmed")
        index = read_json(self.root / "indexes" / "decisions.json")
        self.assertEqual(index["decisions"][decision["decision_id"]]["status"], "confirmed")

    def tearDown(self):
        self.tmp.cleanup()

    def test_missing_main_reason_is_rejected(self):
        with self.assertRaises(ValueError):
            record_decision(self.root, {
                "title": "主角背叛",
                "content": "主角背叛朋友",
                "direct_purpose": "增加冲突",
                "expected_effect": "提高风险",
                "alternatives": [],
                "affected_objects": [],
            })

    def test_confirmation_requires_exact_or_single_pending_target(self):
        self.assertFalse(is_explicit_confirmation("都可以", ["DEC-0001"]))
        self.assertTrue(is_explicit_confirmation("确认", ["DEC-0001"]))
        self.assertTrue(is_explicit_confirmation("接受 DEC-0001", ["DEC-0001"]))

    def test_negative_and_fuzzy_markers_are_rejected(self):
        for text in ("不可以", "不行", "随便 DEC-0001", "你决定 DEC-0001"):
            with self.subTest(text=text):
                self.assertFalse(is_explicit_confirmation(text, ["DEC-0001"]))
        self.assertFalse(is_explicit_confirmation("确认", ["DEC-0001", "DEC-0002"]))
        self.assertTrue(is_explicit_confirmation("接受 DEC-0001", ["DEC-0001", "DEC-0002"]))
        self.assertFalse(
            is_explicit_confirmation("确认 DEC-0001 DEC-0002", ["DEC-0001", "DEC-0002"])
        )

    def test_natural_explicit_id_phrases_are_accepted(self):
        for text in ("好的，接受 DEC-0001", "嗯，确认 DEC-0001"):
            with self.subTest(text=text):
                self.assertTrue(is_explicit_confirmation(text, ["DEC-0001"]))
        self.assertTrue(
            is_explicit_confirmation("好的，接受 DEC-0001", ["DEC-0001", "DEC-0002"])
        )

    def test_direct_negations_and_non_verb_id_are_rejected(self):
        for text in (
            "不接受 DEC-0001",
            "不确认 DEC-0001",
            "不同意 DEC-0001",
            "拒绝接受 DEC-0001",
            "未接受 DEC-0001",
            "按 DEC-0001",
        ):
            with self.subTest(text=text):
                self.assertFalse(is_explicit_confirmation(text, ["DEC-0001"]))

    def test_repeated_confirmation_is_rejected_without_new_event(self):
        from ch_write.io import read_jsonl
        decision = record_decision(self.root, {
            "title": "主角背叛",
            "content": "主角背叛朋友",
            "main_reason": "让忠诚主题产生代价",
            "direct_purpose": "把人物推进不可逆选择",
            "expected_effect": "读者看到关系的破裂",
            "alternatives": [],
            "affected_objects": ["CHR-0001"],
        })
        confirm_decision(self.root, decision["decision_id"], "接受 " + decision["decision_id"])
        before = len(read_jsonl(self.root / "logs" / "decisions.jsonl"))
        with self.assertRaises(ValueError):
            confirm_decision(self.root, decision["decision_id"], "确认 " + decision["decision_id"])
        self.assertEqual(len(read_jsonl(self.root / "logs" / "decisions.jsonl")), before)

    def test_confirm_rejects_non_pending_terminal_statuses(self):
        from ch_write.io import read_json, write_json_atomic
        index_path = self.root / "indexes" / "decisions.json"
        for status in ("rejected", "withdrawn", "superseded", "waived"):
            with self.subTest(status=status):
                decision = record_decision(self.root, {
                    "title": "主角背叛",
                    "content": "主角背叛朋友",
                    "main_reason": "让忠诚主题产生代价",
                    "direct_purpose": "把人物推进不可逆选择",
                    "expected_effect": "读者看到关系的破裂",
                    "alternatives": [],
                    "affected_objects": ["CHR-0001"],
                })
                index = read_json(index_path)
                index["decisions"][decision["decision_id"]]["status"] = status
                write_json_atomic(index_path, index)
                with self.assertRaises(ValueError):
                    confirm_decision(
                        self.root,
                        decision["decision_id"],
                        "接受 " + decision["decision_id"],
                    )

    def test_cli_confirm_rejects_fuzzy_author_statement(self):
        import subprocess
        import sys
        decision = record_decision(self.root, {
            "title": "主角背叛",
            "content": "主角背叛朋友",
            "main_reason": "让忠诚主题产生代价",
            "direct_purpose": "把人物推进不可逆选择",
            "expected_effect": "读者看到关系的破裂",
            "alternatives": [],
            "affected_objects": ["CHR-0001"],
        })
        script = Path(__file__).resolve().parents[1] / "scripts" / "story_project.py"
        result = subprocess.run(
            [
                sys.executable,
                "-B",
                str(script),
                "confirm",
                "--root",
                str(self.root),
                "--id",
                decision["decision_id"],
                "--author-statement",
                "都可以",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertNotEqual(result.returncode, 0)

    def test_profile_change_is_recorded(self):
        from ch_write.decisions import set_interaction_profile
        result = set_interaction_profile(self.root, "fast", "作者要求加快交互")
        self.assertEqual(result["interaction_profile"], "fast")
        self.assertTrue((self.root / "logs" / "decisions.jsonl").is_file())

    def test_confirmed_decision_records_reason_and_statement(self):
        decision = record_decision(self.root, {
            "title": "主角背叛",
            "content": "主角背叛朋友",
            "main_reason": "让忠诚主题产生代价",
            "direct_purpose": "把人物推进不可逆选择",
            "expected_effect": "读者看到关系的破裂",
            "alternatives": [{"text": "不背叛", "rejected_reason": "冲突会消失"}],
            "affected_objects": ["CHR-0001"],
        })
        result = confirm_decision(self.root, decision["decision_id"], "接受 DEC-0001")
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(result["main_reason"], "让忠诚主题产生代价")
        self.assertEqual(result["author_statement"], "接受 DEC-0001")
