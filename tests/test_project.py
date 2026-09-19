import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ch_write.io import append_jsonl, read_json, read_jsonl, write_json_atomic
from ch_write.project import init_project, load_project

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "story_project.py"

LAYOUT = (
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

BALANCED_PROFILE = {
    "preset": "balanced",
    "question_depth": "focused",
    "confirmation_granularity": "batch",
    "version_cadence": "act",
    "output_detail": "standard",
}


class TestProject(unittest.TestCase):
    def test_init_creates_layout_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            returned = init_project(root, "Story", "markdown", "balanced")
            data = load_project(root)

            self.assertEqual(returned, root)
            self.assertEqual(data["schema_version"], 1)
            self.assertEqual(data["name"], "Story")
            self.assertEqual(data["master_formats"], {"lists": "json", "script": "markdown"})
            self.assertEqual(data["interaction_profile"], BALANCED_PROFILE)
            self.assertIsNone(data["active_version"])
            self.assertTrue(data["created_at"])
            for rel in LAYOUT:
                self.assertTrue((root / rel).is_dir(), rel)
            self.assertTrue((root / "project.json").is_file())

    def test_duplicate_init_does_not_overwrite_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            original = read_json(root / "project.json")

            with self.assertRaises(FileExistsError):
                init_project(root, "Replacement", "fountain", "fast")

            self.assertEqual(read_json(root / "project.json"), original)

    def test_init_rejects_invalid_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.subTest(field="profile"):
                with self.assertRaises(ValueError):
                    init_project(Path(tmp) / "profile", "Story", "markdown", "invalid")
            with self.subTest(field="script_master"):
                with self.assertRaises(ValueError):
                    init_project(Path(tmp) / "script", "Story", "docx", "balanced")
            with self.subTest(field="name"):
                with self.assertRaises(ValueError):
                    init_project(Path(tmp) / "name", "", "markdown", "balanced")

    def test_json_and_jsonl_io_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            json_path = root / "nested" / "data.json"
            jsonl_path = root / "records.jsonl"
            payload = {"name": "星杯"}
            records = ({"sequence": 1}, {"sequence": 2})

            write_json_atomic(json_path, payload)
            for record in records:
                append_jsonl(jsonl_path, record)

            self.assertEqual(read_json(json_path), payload)
            self.assertEqual(read_jsonl(jsonl_path), list(records))
            self.assertFalse(list(json_path.parent.glob("*.tmp")))


class TestProjectCli(unittest.TestCase):
    def test_init_command_creates_project(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPT),
                    "init",
                    "--root",
                    str(root),
                    "--name",
                    "Story",
                    "--script-master",
                    "markdown",
                    "--interaction-profile",
                    "balanced",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(load_project(root)["interaction_profile"], BALANCED_PROFILE)


if __name__ == "__main__":
    unittest.main()
