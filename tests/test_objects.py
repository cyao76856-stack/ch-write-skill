import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ch_write.project import init_project
from ch_write.ids import allocate_id
from ch_write.objects import (
    add_object, add_relation, merge_objects, rename_object, set_object_confirmed,
    tombstone_object, update_object,
)

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "story_project.py"


def read_jsonl(path):
    return [
        json.loads(line)
        for line in Path(path).read_text("utf-8").splitlines()
        if line.strip()
    ]


class TestObjects(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "story"
        init_project(self.root, "Story", "markdown", "balanced")

    def tearDown(self):
        self.tmp.cleanup()

    def test_ids_never_reused_and_same_names_stay_distinct(self):
        a = add_object(self.root, "character", "托里昂", {"role": "official"})
        b = add_object(self.root, "character", "托里昂", {"role": "merchant"})
        self.assertEqual(a["object_id"], "CHR-0001")
        self.assertEqual(b["object_id"], "CHR-0002")
        self.assertNotEqual(a["object_id"], b["object_id"])

    def test_rename_keeps_id_and_alias(self):
        obj = add_object(self.root, "location", "贝尔", {})
        renamed = rename_object(self.root, obj["object_id"], "贝尔港")
        self.assertEqual(renamed["object_id"], obj["object_id"])
        self.assertIn("贝尔", renamed["aliases"])
        self.assertNotIn("贝尔", obj["aliases"])

    def test_rename_to_current_name_does_not_add_alias(self):
        obj = add_object(self.root, "location", "贝尔", {})
        renamed = rename_object(self.root, obj["object_id"], "贝尔")
        self.assertEqual(renamed["object_id"], obj["object_id"])
        self.assertEqual(renamed["aliases"], [])
        self.assertEqual(obj["aliases"], [])

    def test_merge_and_tombstone_preserve_history(self):
        a = add_object(self.root, "faction", "迦南", {})
        b = add_object(self.root, "faction", "旧迦南", {})
        add_relation(self.root, a["object_id"], "same_as", b["object_id"])
        merged = merge_objects(self.root, a["object_id"], b["object_id"], "作者确认")
        self.assertEqual(merged["object_id"], a["object_id"])
        entities = json.loads(
            (self.root / "indexes" / "entities.json").read_text("utf-8")
        )["objects"]
        self.assertTrue(entities[b["object_id"]]["tombstoned"])
        self.assertEqual(entities[b["object_id"]]["merged_into"], a["object_id"])
        deleted = tombstone_object(self.root, a["object_id"], "测试删除")
        self.assertEqual(deleted["status"], "tombstoned")


class TestObjectStorage(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "story"
        init_project(self.root, "Story", "markdown", "balanced")

    def tearDown(self):
        self.tmp.cleanup()

    def test_allocate_id_scans_index_and_logs(self):
        self.assertEqual(allocate_id(self.root, "character"), "CHR-0001")
        add_object(self.root, "character", "甲", {})
        add_object(self.root, "character", "乙", {})
        self.assertEqual(allocate_id(self.root, "character"), "CHR-0003")

    def test_update_object_appends_revision_without_changing_id(self):
        obj = add_object(self.root, "item", "戒指", {"material": "gold"})
        updated = update_object(self.root, obj["object_id"], {"material": "silver"})
        self.assertEqual(updated["object_id"], obj["object_id"])
        self.assertEqual(updated["revision"], "rev-0002")
        self.assertEqual(updated["attributes"]["material"], "silver")
        self.assertEqual(obj["attributes"]["material"], "gold")
        log = (self.root / "store" / "objects" / "item.jsonl").read_text("utf-8").splitlines()
        self.assertEqual(len(log), 2)

    def test_later_operation_does_not_mutate_earlier_snapshot(self):
        a = add_object(self.root, "character", "甲", {"role": "official"})
        b = add_object(self.root, "character", "乙", {"role": "merchant"})
        snapshot_b = json.loads(json.dumps(b))
        rename_object(self.root, a["object_id"], "甲改")
        tombstone_object(self.root, a["object_id"], "测试删除")
        self.assertEqual(b["name"], snapshot_b["name"])
        self.assertEqual(b["status"], snapshot_b["status"])
        self.assertEqual(b["attributes"], snapshot_b["attributes"])
        self.assertEqual(b["revision"], snapshot_b["revision"])

    def test_add_relation_validates_and_records(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "event", "B", {})
        with self.assertRaises(ValueError):
            add_relation(self.root, a["object_id"], "not_a_relation", b["object_id"])
        relation = add_relation(self.root, a["object_id"], "causes", b["object_id"], {"quote": "证据"})
        self.assertEqual(relation["relation_id"], "REL-0001")
        self.assertEqual(relation["relation"], "causes")
        self.assertTrue((self.root / "store" / "relations.jsonl").is_file())
        index = json.loads((self.root / "indexes" / "relations.json").read_text("utf-8"))
        self.assertEqual(len(index["relations"]), 1)

    def test_add_relation_rejects_tombstoned_or_merged_endpoint(self):
        a = add_object(self.root, "character", "A", {})
        b = add_object(self.root, "character", "B", {})
        c = add_object(self.root, "character", "C", {})
        tombstone_object(self.root, b["object_id"], "删除")
        with self.assertRaises(ValueError):
            add_relation(self.root, a["object_id"], "knows", b["object_id"])
        with self.assertRaises(ValueError):
            add_relation(self.root, b["object_id"], "knows", a["object_id"])

        d = add_object(self.root, "character", "D", {})
        e = add_object(self.root, "character", "E", {})
        merge_objects(self.root, d["object_id"], e["object_id"], "合并")
        with self.assertRaises(ValueError):
            add_relation(self.root, c["object_id"], "knows", e["object_id"])

    def test_merge_rewrites_relations_and_keeps_mapping(self):
        a = add_object(self.root, "faction", "A", {})
        b = add_object(self.root, "faction", "B", {})
        c = add_object(self.root, "item", "C", {})
        add_relation(self.root, a["object_id"], "knows", b["object_id"])
        add_relation(self.root, b["object_id"], "owns", c["object_id"])
        merge_objects(self.root, a["object_id"], b["object_id"], "合并")
        entities = json.loads((self.root / "indexes" / "entities.json").read_text("utf-8"))["objects"]
        self.assertEqual(entities[b["object_id"]]["merged_into"], a["object_id"])
        self.assertIn(b["object_id"], entities[a["object_id"]]["merged_from"])
        index = json.loads((self.root / "indexes" / "relations.json").read_text("utf-8"))
        relations = index["relations"]
        self.assertEqual(relations[1]["source_id"], a["object_id"])
        self.assertEqual(relations[1]["target_id"], c["object_id"])

    def test_relation_log_and_index_agree_on_effective_state(self):
        a = add_object(self.root, "faction", "A", {})
        b = add_object(self.root, "faction", "B", {})
        c = add_object(self.root, "item", "C", {})
        first = add_relation(self.root, a["object_id"], "knows", b["object_id"])
        second = add_relation(self.root, b["object_id"], "owns", c["object_id"])
        merge_objects(self.root, a["object_id"], b["object_id"], "合并")

        log = read_jsonl(self.root / "store" / "relations.jsonl")
        self.assertEqual(len(log), 4)
        self.assertEqual(log[0]["relation_id"], first["relation_id"])
        self.assertEqual(log[0]["source_id"], a["object_id"])
        self.assertEqual(log[0]["target_id"], b["object_id"])
        self.assertEqual(log[1]["relation_id"], second["relation_id"])
        self.assertEqual(log[1]["source_id"], b["object_id"])
        self.assertEqual(log[1]["target_id"], c["object_id"])

        index = json.loads((self.root / "indexes" / "relations.json").read_text("utf-8"))
        active = [rel for rel in index["relations"] if rel["status"] == "active"]
        self.assertEqual(len(active), 1)
        self.assertEqual(active[0]["source_id"], a["object_id"])
        self.assertEqual(active[0]["target_id"], c["object_id"])
        self.assertEqual(active[0]["relation"], "owns")
        self.assertEqual(active[0]["supersedes"], second["relation_id"])
        self.assertEqual(log[-1]["relation_id"], active[0]["relation_id"])
        self.assertEqual(log[-1]["source_id"], active[0]["source_id"])
        self.assertEqual(log[-1]["target_id"], active[0]["target_id"])
        self.assertEqual(log[-1]["status"], active[0]["status"])
        self.assertEqual(log[-1]["supersedes"], active[0]["supersedes"])

    def test_self_reference_is_not_active_after_merge(self):
        a = add_object(self.root, "faction", "A", {})
        b = add_object(self.root, "faction", "B", {})
        original = add_relation(self.root, a["object_id"], "knows", b["object_id"])
        merge_objects(self.root, a["object_id"], b["object_id"], "合并")

        log = read_jsonl(self.root / "store" / "relations.jsonl")
        self.assertEqual(len(log), 2)
        self.assertEqual(log[0]["relation_id"], original["relation_id"])
        self.assertEqual(log[0]["status"], "active")
        self.assertEqual(log[1]["status"], "withdrawn")
        self.assertEqual(log[1]["supersedes"], original["relation_id"])

        index = json.loads((self.root / "indexes" / "relations.json").read_text("utf-8"))
        active = [rel for rel in index["relations"] if rel["status"] == "active"]
        self.assertEqual(active, [])
        self.assertEqual(index["relations"][0]["status"], "withdrawn")
        self.assertEqual(index["relations"][0]["source_id"], a["object_id"])
        self.assertEqual(index["relations"][0]["target_id"], a["object_id"])

    def test_tombstone_keeps_name_in_index(self):
        obj = add_object(self.root, "location", "贝尔", {})
        tombstone_object(self.root, obj["object_id"], "删除")
        entities = json.loads((self.root / "indexes" / "entities.json").read_text("utf-8"))["objects"]
        self.assertEqual(entities[obj["object_id"]]["name"], "贝尔")
        self.assertTrue(entities[obj["object_id"]]["tombstoned"])


    def test_add_object_defaults_to_proposed_and_excluded(self):
        obj = add_object(self.root, "character", "A", {})
        self.assertEqual(obj["provenance"], "proposed")
        self.assertEqual(obj["source_refs"], [])
        self.assertEqual(obj["canon_membership"], "excluded")
        entities = json.loads((self.root / "indexes" / "entities.json").read_text("utf-8"))["objects"]
        entity = entities[obj["object_id"]]
        self.assertEqual(entity["provenance"], "proposed")
        self.assertEqual(entity["source_refs"], [])
        self.assertEqual(entity["canon_membership"], "excluded")
        log = read_jsonl(self.root / "store" / "objects" / "character.jsonl")
        self.assertEqual(log[-1]["provenance"], "proposed")
        self.assertEqual(log[-1]["source_refs"], [])
        self.assertEqual(log[-1]["canon_membership"], "excluded")

    def test_add_object_rejects_reserved_storage_types(self):
        for object_type in ("source", "decision", "change", "relation"):
            with self.subTest(object_type=object_type):
                with self.assertRaises(ValueError):
                    add_object(self.root, object_type, "不应进入叙事对象", {})

    def test_confirmation_promotes_active_and_edit_marks_stale(self):
        obj = add_object(self.root, "character", "A", {})
        set_object_confirmed(self.root, obj["object_id"], "v001")
        entities = json.loads((self.root / "indexes" / "entities.json").read_text("utf-8"))["objects"]
        self.assertEqual(entities[obj["object_id"]]["canon_membership"], "active")
        self.assertEqual(entities[obj["object_id"]]["canon_version"], "v001")

        updated = update_object(self.root, obj["object_id"], {"role": "king"})
        self.assertEqual(updated["canon_membership"], "stale")
        entities = json.loads((self.root / "indexes" / "entities.json").read_text("utf-8"))["objects"]
        self.assertEqual(entities[obj["object_id"]]["canon_membership"], "stale")

    def test_merge_marks_active_survivor_stale(self):
        a = add_object(self.root, "faction", "A", {})
        b = add_object(self.root, "faction", "B", {})
        set_object_confirmed(self.root, a["object_id"], "v001")
        set_object_confirmed(self.root, b["object_id"], "v001")
        merge_objects(self.root, a["object_id"], b["object_id"], "合并")
        entities = json.loads((self.root / "indexes" / "entities.json").read_text("utf-8"))["objects"]
        self.assertEqual(entities[a["object_id"]]["canon_membership"], "stale")
        self.assertEqual(entities[b["object_id"]]["canon_membership"], "stale")

    def test_merge_rejects_tombstoned_ids_before_mutation(self):
        a = add_object(self.root, "faction", "A", {})
        b = add_object(self.root, "faction", "B", {})
        tombstone_object(self.root, b["object_id"], "删除")
        log_path = self.root / "store" / "objects" / "faction.jsonl"
        before = log_path.read_text("utf-8").splitlines()
        with self.assertRaises(ValueError):
            merge_objects(self.root, a["object_id"], b["object_id"], "合并")
        with self.assertRaises(ValueError):
            merge_objects(self.root, b["object_id"], a["object_id"], "合并")
        self.assertEqual(log_path.read_text("utf-8").splitlines(), before)

    def test_merge_rejects_merged_ids_before_mutation(self):
        a = add_object(self.root, "faction", "A", {})
        b = add_object(self.root, "faction", "B", {})
        merge_objects(self.root, a["object_id"], b["object_id"], "合并")
        log_path = self.root / "store" / "objects" / "faction.jsonl"
        before = log_path.read_text("utf-8").splitlines()
        with self.assertRaises(ValueError):
            merge_objects(self.root, a["object_id"], b["object_id"], "再次合并")
        with self.assertRaises(ValueError):
            merge_objects(self.root, b["object_id"], a["object_id"], "再次合并")
        self.assertEqual(log_path.read_text("utf-8").splitlines(), before)

    def test_set_object_confirmed_rejects_tombstoned_or_merged(self):
        a = add_object(self.root, "location", "A", {})
        tombstone_object(self.root, a["object_id"], "删除")
        with self.assertRaises(ValueError):
            set_object_confirmed(self.root, a["object_id"], "v001")

        b = add_object(self.root, "location", "B", {})
        c = add_object(self.root, "location", "C", {})
        merge_objects(self.root, b["object_id"], c["object_id"], "合并")
        with self.assertRaises(ValueError):
            set_object_confirmed(self.root, c["object_id"], "v001")

    def test_update_rename_tombstone_reject_non_active_objects(self):
        obj = add_object(self.root, "location", "贝尔", {})
        tombstone_object(self.root, obj["object_id"], "删除")
        with self.assertRaises(ValueError):
            update_object(self.root, obj["object_id"], {"x": 1})
        with self.assertRaises(ValueError):
            rename_object(self.root, obj["object_id"], "贝尔港")
        with self.assertRaises(ValueError):
            tombstone_object(self.root, obj["object_id"], "再次删除")

class TestObjectCli(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )

    def test_object_cli_rejects_reserved_storage_types(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            for object_type in ("source", "decision", "change", "relation"):
                with self.subTest(object_type=object_type):
                    result = self.run_cli(
                        "object", "add", "--root", str(root), "--type", object_type,
                        "--name", "保留前缀",
                    )
                    self.assertNotEqual(result.returncode, 0)

    def test_object_add_and_relation_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            added = self.run_cli(
                "object", "add", "--root", str(root), "--type", "character",
                "--name", "甲", "--attribute", "role=official",
            )
            self.assertEqual(added.returncode, 0, added.stderr)
            first = json.loads(added.stdout)
            self.assertEqual(first["object_id"], "CHR-0001")
            second_result = self.run_cli(
                "object", "add", "--root", str(root), "--type", "character",
                "--name", "乙",
            )
            self.assertEqual(second_result.returncode, 0, second_result.stderr)
            second = json.loads(second_result.stdout)
            related = self.run_cli(
                "object", "relation", "--root", str(root),
                "--source", first["object_id"], "--relation", "knows",
                "--target", second["object_id"],
            )
            self.assertEqual(related.returncode, 0, related.stderr)
            relation = json.loads(related.stdout)
            self.assertEqual(relation["relation_id"], "REL-0001")


if __name__ == "__main__":
    unittest.main()