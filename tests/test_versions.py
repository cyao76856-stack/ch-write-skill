import json
import tempfile
import unittest
from pathlib import Path
from ch_write.project import init_project
from ch_write.objects import add_object, tombstone_object, update_object
from ch_write.decisions import record_decision, confirm_decision
from ch_write.versions import (
    archive_version,
    confirm_batch,
    get_status,
    mark_tampered,
    restore_version,
    snapshot_working,
)

class TestVersions(unittest.TestCase):
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
        confirm_decision(self.root, decision["decision_id"], "接受 " + decision["decision_id"])
        return decision

    def test_snapshot_then_confirmed_batch_creates_manifest(self):
        char = add_object(self.root, "character", "奥古斯都", {"role": "envoy"})
        snapshot = snapshot_working(self.root, "initial")
        self.assertTrue(snapshot["snapshot_id"].startswith("PRP-"))
        decision = self._record_and_confirm("确认人物", [char["object_id"]])
        version = confirm_batch(
            self.root,
            "BATCH-001",
            [decision["decision_id"]],
            {char["object_id"]: char["revision"]},
        )
        self.assertEqual(version, "v001")
        manifest = json.loads((self.root / "versions" / "v001" / "manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["parent"], None)
        self.assertEqual(manifest["objects"][char["object_id"]], char["revision"])
        self.assertFalse((self.root / "versions" / "v001" / "objects").exists())
        status = get_status(self.root)
        self.assertEqual(status["active_version"], "v001")

    def test_snapshot_writes_proposal_index_and_patch(self):
        add_object(self.root, "character", "奥古斯都", {"role": "envoy"})
        snapshot = snapshot_working(self.root, "initial")
        index_path = self.root / "proposals" / "index.jsonl"
        patch_path = self.root / "proposals" / "patches" / f'{snapshot["snapshot_id"]}.json'
        self.assertTrue(index_path.is_file())
        self.assertTrue(patch_path.is_file())
        self.assertEqual(snapshot["label"], "initial")

    def test_confirm_batch_rejects_unconfirmed_decision(self):
        add_object(self.root, "character", "奥古斯都", {"role": "envoy"})
        decision = record_decision(self.root, {
            "title": "确认人物",
            "content": "建立奥古斯都",
            "main_reason": "承担幕后操纵功能",
            "direct_purpose": "推动权力冲突",
            "expected_effect": "制造信息差",
            "alternatives": [],
            "affected_objects": ["CHR-0001"],
        })
        with self.assertRaises(ValueError):
            confirm_batch(self.root, "BATCH-001", [decision["decision_id"]], {"CHR-0001": "rev-0001"})

    def test_second_version_inherits_unchanged_objects(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "location", "B", {})
        decision = self._record_and_confirm("确认初始对象", [a["object_id"], b["object_id"]])
        self.assertEqual(
            confirm_batch(
                self.root,
                "B-1",
                [decision["decision_id"]],
                {a["object_id"]: a["revision"], b["object_id"]: b["revision"]},
            ),
            "v001",
        )
        updated = update_object(self.root, a["object_id"], {"role": "king"})
        decision2 = self._record_and_confirm("确认更新", [a["object_id"]])
        self.assertEqual(
            confirm_batch(
                self.root,
                "B-2",
                [decision2["decision_id"]],
                {a["object_id"]: updated["revision"]},
            ),
            "v002",
        )
        manifest = json.loads((self.root / "versions" / "v002" / "manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["parent"], "v001")
        self.assertEqual(manifest["objects"][a["object_id"]], updated["revision"])
        self.assertEqual(manifest["objects"][b["object_id"]], b["revision"])

    def test_partial_object_revisions_inherit_active_parent_objects(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "location", "B", {})
        decision = self._record_and_confirm("确认初始对象", [a["object_id"], b["object_id"]])
        confirm_batch(
            self.root,
            "B-1",
            [decision["decision_id"]],
            {a["object_id"]: a["revision"], b["object_id"]: b["revision"]},
        )
        updated = update_object(self.root, a["object_id"], {"role": "king"})
        decision2 = self._record_and_confirm("确认更新", [a["object_id"]])
        version = confirm_batch(
            self.root,
            "B-2",
            [decision2["decision_id"]],
            {a["object_id"]: updated["revision"]},
        )
        self.assertEqual(version, "v002")
        manifest = json.loads((self.root / "versions" / "v002" / "manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["objects"][b["object_id"]], b["revision"])

    def test_mark_tampered_records_status_without_repairing(self):
        add_object(self.root, "character", "奥古斯都", {"role": "envoy"})
        snapshot = snapshot_working(self.root, "initial")
        decision = self._record_and_confirm("确认人物", ["CHR-0001"])
        confirm_batch(self.root, "B-1", [decision["decision_id"]], snapshot["objects"])
        result = mark_tampered(self.root, "versions/v001/manifest.json", "检测到修改")
        self.assertEqual(result["status"], "tampered")
        status = get_status(self.root)
        self.assertEqual(status["versions"]["v001"]["status"], "tampered")

    def test_stale_object_revision_cannot_be_confirmed(self):
        a = add_object(self.root, "character", "A", {})
        old_revision = a["revision"]
        update_object(self.root, a["object_id"], {"role": "king"})
        decision = self._record_and_confirm("确认更新", [a["object_id"]])
        with self.assertRaises(ValueError):
            confirm_batch(
                self.root,
                "B-1",
                [decision["decision_id"]],
                {a["object_id"]: old_revision},
            )

    def test_initial_version_includes_only_referenced_objects(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "location", "B", {})
        decision = self._record_and_confirm("确认初始版本", [a["object_id"]])
        version = confirm_batch(
            self.root,
            "B-1",
            [decision["decision_id"]],
            {a["object_id"]: a["revision"]},
        )
        self.assertEqual(version, "v001")
        manifest = json.loads((self.root / "versions" / "v001" / "manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["objects"][a["object_id"]], a["revision"])
        self.assertNotIn(b["object_id"], manifest["objects"])

    def test_initial_version_rejects_unreferenced_object_revision(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "location", "B", {})
        decision = self._record_and_confirm("确认人物", [a["object_id"]])
        with self.assertRaises(ValueError):
            confirm_batch(
                self.root,
                "B-1",
                [decision["decision_id"]],
                {a["object_id"]: a["revision"], b["object_id"]: b["revision"]},
            )

    def test_batch_only_repromotes_referenced_objects(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "location", "B", {})
        decision = self._record_and_confirm("确认初始 A", [a["object_id"]])
        confirm_batch(
            self.root,
            "B-1",
            [decision["decision_id"]],
            {a["object_id"]: a["revision"]},
        )
        a_v001_revision = a["revision"]
        entities = json.loads((self.root / "indexes" / "entities.json").read_text("utf-8"))["objects"]
        self.assertEqual(entities[a["object_id"]]["canon_membership"], "active")
        self.assertEqual(entities[a["object_id"]]["canon_version"], "v001")

        updated = update_object(self.root, a["object_id"], {"role": "king"})
        self.assertNotEqual(updated["revision"], a_v001_revision)
        entities = json.loads((self.root / "indexes" / "entities.json").read_text("utf-8"))["objects"]
        self.assertEqual(entities[a["object_id"]]["canon_membership"], "stale")

        decision2 = self._record_and_confirm("确认 B", [b["object_id"]])
        confirm_batch(
            self.root,
            "B-2",
            [decision2["decision_id"]],
            {b["object_id"]: b["revision"]},
        )

        entities = json.loads((self.root / "indexes" / "entities.json").read_text("utf-8"))["objects"]
        self.assertEqual(entities[a["object_id"]]["canon_membership"], "stale")
        self.assertEqual(entities[a["object_id"]]["canon_version"], "v001")
        self.assertEqual(entities[b["object_id"]]["canon_membership"], "active")
        self.assertEqual(entities[b["object_id"]]["canon_version"], "v002")

        manifest = json.loads((self.root / "versions" / "v002" / "manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["objects"][a["object_id"]], a_v001_revision)
        self.assertEqual(manifest["objects"][b["object_id"]], b["revision"])

    def test_later_version_removes_tombstoned_parent_object(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "location", "B", {})
        decision = self._record_and_confirm("确认初始对象", [a["object_id"], b["object_id"]])
        confirm_batch(
            self.root,
            "B-1",
            [decision["decision_id"]],
            {a["object_id"]: a["revision"], b["object_id"]: b["revision"]},
        )
        tombstone_object(self.root, b["object_id"], "作者确认删除")
        decision2 = self._record_and_confirm("确认继续", [a["object_id"]])
        version = confirm_batch(
            self.root,
            "B-2",
            [decision2["decision_id"]],
            {a["object_id"]: a["revision"]},
        )
        self.assertEqual(version, "v002")
        manifest = json.loads((self.root / "versions" / "v002" / "manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["objects"][a["object_id"]], a["revision"])
        self.assertNotIn(b["object_id"], manifest["objects"])
        self.assertIn(b["object_id"], manifest["removed"])

    def test_top_level_tamper_status_is_visible(self):
        result = mark_tampered(self.root, "working/notes.md", "检测到修改")
        self.assertEqual(result["status"], "tampered")
        status = get_status(self.root)
        self.assertIn("working/notes.md", status["files"])
        self.assertEqual(status["files"]["working/notes.md"]["status"], "tampered")

    def test_restore_version_refuses_nonempty_target(self):
        add_object(self.root, "character", "A", {})
        decision = self._record_and_confirm("确认人物", ["CHR-0001"])
        confirm_batch(self.root, "B-1", [decision["decision_id"]], {"CHR-0001": "rev-0001"})
        target = Path(self.tmp.name) / "restored"
        target.mkdir()
        existing = target / "keep.txt"
        existing.write_text("do not overwrite", encoding="utf-8")

        with self.assertRaises(FileExistsError):
            restore_version(self.root, "v001", target)
        self.assertEqual(existing.read_text("utf-8"), "do not overwrite")

    def test_restore_version_writes_empty_target(self):
        obj = add_object(self.root, "character", "A", {})
        decision = self._record_and_confirm("确认人物", [obj["object_id"]])
        confirm_batch(self.root, "B-1", [decision["decision_id"]], {obj["object_id"]: obj["revision"]})
        target = Path(self.tmp.name) / "restored"
        result = restore_version(self.root, "v001", target)
        self.assertEqual(result["objects_restored"], 1)
        self.assertTrue((target / "manifest.json").is_file())
        self.assertTrue((target / "objects" / f"{obj['object_id']}.json").is_file())

    def test_archive_overwrite_is_rejected(self):
        add_object(self.root, "character", "奥古斯都", {"role": "envoy"})
        snapshot = snapshot_working(self.root, "initial")
        decision = self._record_and_confirm("确认人物", ["CHR-0001"])
        confirm_batch(self.root, "B-1", [decision["decision_id"]], snapshot["objects"])
        archive_version(self.root, "v001")
        with self.assertRaises(FileExistsError):
            archive_version(self.root, "v001")

if __name__ == "__main__":
    unittest.main()
