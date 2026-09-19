import json
import tempfile
import unittest
from pathlib import Path

from ch_write.project import init_project
from ch_write.objects import add_object, add_relation, tombstone_object
from ch_write.decisions import record_decision, confirm_decision
from ch_write.versions import confirm_batch, mark_tampered, snapshot_working
from ch_write.sources import register_sources
from ch_write.io import read_json, write_json_atomic, append_jsonl
from ch_write.validation import impact, validate_project


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "story"
        init_project(self.root, "Story", "markdown", "balanced")

    def tearDown(self):
        self.tmp.cleanup()

    def _record_and_confirm(self, title, object_ids):
        decision = record_decision(self.root, {
            "title": title,
            "content": title,
            "main_reason": "测试理由",
            "direct_purpose": "测试目的",
            "expected_effect": "测试效果",
            "alternatives": [],
            "affected_objects": list(object_ids),
        })
        confirm_decision(
            self.root, decision["decision_id"], "接受 " + decision["decision_id"]
        )
        return decision

    def _create_version(self, object_ids):
        snapshot = snapshot_working(self.root, "initial")
        decision = self._record_and_confirm("确认版本", object_ids)
        version = confirm_batch(
            self.root,
            "BATCH-001",
            [decision["decision_id"]],
            snapshot["objects"],
        )
        return version

    def _any_gate(self, report, code):
        return any(
            item.get("severity") == "gate" and item.get("code") == code
            for item in report
        )

    def test_impact_returns_direct_and_indirect_objects(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "event", "B", {})
        c = add_object(self.root, "location", "C", {})
        add_relation(self.root, a["object_id"], "causes", b["object_id"])
        add_relation(self.root, b["object_id"], "appears_in", c["object_id"])
        report = impact(self.root, a["object_id"])
        self.assertIn(b["object_id"], report["direct"])
        self.assertIn(c["object_id"], report["indirect"])

    def test_validation_reports_missing_reference(self):
        report = validate_project(self.root)
        self.assertIsInstance(report, list)
        self.assertTrue(all("severity" in item for item in report))

    def test_impact_returns_full_shape(self):
        obj = add_object(self.root, "character", "A", {})
        report = impact(self.root, obj["object_id"])
        self.assertEqual(report["object_id"], obj["object_id"])
        for key in ("direct", "indirect", "by_category", "classification"):
            self.assertIn(key, report)
        for key in ("must_change", "may_change", "review_only"):
            self.assertIn(key, report["classification"])

    def test_impact_unknown_object_raises(self):
        with self.assertRaises(ValueError):
            impact(self.root, "CHR-9999")

    def test_validation_detects_missing_relation_target_in_index(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "event", "B", {})
        relation = add_relation(self.root, a["object_id"], "causes", b["object_id"])
        index = read_json(self.root / "indexes" / "relations.json")
        index["relations"].append({
            "relation_id": "REL-9999",
            "source_id": a["object_id"],
            "relation": "causes",
            "target_id": "CHR-9999",
            "evidence": None,
            "revision": "rev-0001",
            "status": "active",
            "supersedes": None,
            "created_at": relation["created_at"],
        })
        write_json_atomic(self.root / "indexes" / "relations.json", index)
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "relation_missing_target"))

    def test_validation_detects_tombstoned_relation_target(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "event", "B", {})
        add_relation(self.root, a["object_id"], "causes", b["object_id"])
        tombstone_object(self.root, b["object_id"], "测试删除")
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "relation_tombstoned_target"))

    def test_validation_detects_unconfirmed_decision_without_author(self):
        decision = self._record_and_confirm("确认决定", ["CHR-0001"])
        index = read_json(self.root / "indexes" / "decisions.json")
        index["decisions"][decision["decision_id"]]["author_statement"] = ""
        write_json_atomic(self.root / "indexes" / "decisions.json", index)
        report = validate_project(self.root)
        self.assertTrue(
            self._any_gate(report, "confirmed_decision_missing_confirmation")
        )

    def test_validation_detects_manifest_missing_revision(self):
        a = add_object(self.root, "character", "A", {})
        self._create_version([a["object_id"]])
        manifest_path = self.root / "versions" / "v001" / "manifest.json"
        manifest = read_json(manifest_path)
        manifest["objects"][a["object_id"]] = "rev-9999"
        write_json_atomic(manifest_path, manifest)
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "manifest_missing_revision"))

    def test_validation_detects_tampered_version(self):
        a = add_object(self.root, "character", "A", {})
        self._create_version([a["object_id"]])
        mark_tampered(
            self.root, "versions/v001/manifest.json", "检测到修改"
        )
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "version_tampered"))

    def test_validation_detects_duplicate_relation_id(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "event", "B", {})
        relation = add_relation(self.root, a["object_id"], "causes", b["object_id"])
        append_jsonl(
            self.root / "store" / "relations.jsonl",
            relation,
        )
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "duplicate_relation_id"))

    def test_validation_detects_source_conflict(self):
        source = Path(self.tmp.name) / "source.txt"
        source.write_text("old", encoding="utf-8")
        register_sources(self.root, [{
            "path": str(source),
            "order": 1,
            "priority": 1,
            "merge_strategy": "primary",
        }])
        source.write_text("new", encoding="utf-8")
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "source_conflict"))

    def test_corrupt_object_jsonl_with_manifest_returns_gate_not_exception(self):
        a = add_object(self.root, "character", "A", {})
        self._create_version([a["object_id"]])
        log_path = self.root / "store" / "objects" / "character.jsonl"
        log_path.write_text("{not-json\n", encoding="utf-8")
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "file_corrupt"))

    def test_malformed_decisions_index_returns_gate_not_exception(self):
        write_json_atomic(
            self.root / "indexes" / "decisions.json",
            {"decisions": []},
        )
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "invalid_decisions_index"))

    def test_non_confirmed_decision_with_canon_items_gates(self):
        add_object(self.root, "character", "A", {})
        decision = record_decision(self.root, {
            "title": "未确认 canon",
            "content": "未确认内容",
            "main_reason": "测试理由",
            "direct_purpose": "测试目的",
            "expected_effect": "测试效果",
            "alternatives": [],
            "affected_objects": ["CHR-0001"],
            "canon_items": ["CHR-0001"],
        })
        report = validate_project(self.root)
        self.assertTrue(
            self._any_gate(report, "canon_has_non_confirmed_status")
        )

    def test_valid_relation_reference_is_accepted(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "event", "B", {})
        relation = add_relation(self.root, a["object_id"], "causes", b["object_id"])
        record_decision(self.root, {
            "title": "关联关系",
            "content": "引用关系编号",
            "main_reason": "测试理由",
            "direct_purpose": "测试目的",
            "expected_effect": "测试效果",
            "alternatives": [],
            "affected_objects": [relation["relation_id"]],
        })
        report = validate_project(self.root)
        self.assertFalse(
            self._any_gate(report, "decision_missing_object_reference")
        )

    def test_missing_relation_index_with_history_gates(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "event", "B", {})
        add_relation(self.root, a["object_id"], "causes", b["object_id"])
        (self.root / "indexes" / "relations.json").unlink()
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "relation_index_missing"))

    def test_missing_relation_index_still_reports_secondary_faults(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "event", "B", {})
        add_relation(self.root, a["object_id"], "causes", b["object_id"])
        tombstone_object(self.root, b["object_id"], "测试删除")
        (self.root / "indexes" / "relations.json").unlink()
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "relation_index_missing"))
        self.assertTrue(self._any_gate(report, "relation_tombstoned_target"))

    def test_malformed_relation_record_type_returns_gate_not_exception(self):
        append_jsonl(
            self.root / "store" / "relations.jsonl",
            {
                "relation_id": ["REL-0001"],
                "source_id": "CHR-0001",
                "relation": "causes",
                "target_id": "EVT-0001",
                "status": "active",
            },
        )
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "malformed_relation_record"))

    def test_malformed_decision_event_type_returns_gate_not_exception(self):
        append_jsonl(
            self.root / "logs" / "decisions.jsonl",
            {
                "decision_id": "DEC-0001",
                "event_type": ["proposed"],
            },
        )
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "malformed_decision_event"))


    def test_corrupt_list_file_returns_gate_not_exception(self):
        (self.root / "store" / "lists").mkdir(parents=True, exist_ok=True)
        (self.root / "store" / "lists" / "structure.json").write_text(
            "{not-json\n", encoding="utf-8"
        )
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "file_corrupt"))

    def test_malformed_list_items_return_gate_not_exception(self):
        (self.root / "store" / "lists").mkdir(parents=True, exist_ok=True)
        (self.root / "store" / "lists" / "structure.json").write_text(
            '{"items": ["bad", {"id": "STR-0001"}]}',
            encoding="utf-8",
        )
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "invalid_list_item"))
        self.assertTrue(self._any_gate(report, "list_item_missing_name"))

    def test_corrupt_timeline_returns_gate_not_exception(self):
        (self.root / "store" / "timeline.jsonl").write_text(
            "{not-json\n", encoding="utf-8"
        )
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "file_corrupt"))

    def test_corrupt_location_states_returns_gate_not_exception(self):
        (self.root / "store" / "location_states.jsonl").write_text(
            "{not-json\n", encoding="utf-8"
        )
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "file_corrupt"))

    def test_malformed_timeline_record_returns_gate_not_exception(self):
        append_jsonl(
            self.root / "store" / "timeline.jsonl",
            {"event_id": "EVT-0001"},
        )
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "invalid_timeline_record"))

    def test_malformed_location_state_record_returns_gate_not_exception(self):
        append_jsonl(
            self.root / "store" / "location_states.jsonl",
            {"location_id": "LOC-0001"},
        )
        report = validate_project(self.root)
        self.assertTrue(self._any_gate(report, "invalid_location_state_record"))


if __name__ == "__main__":
    unittest.main()
