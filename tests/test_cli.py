import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "story_project.py"


class TestCli(unittest.TestCase):
    def test_help_lists_core_commands(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("init", "status", "source", "object", "decision",
                        "change", "snapshot", "confirm", "impact",
                        "validate", "render", "archive", "restore"):
            self.assertIn(command, result.stdout)

    def test_help_lists_full_interface(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in ("init", "status", "profile", "source", "object",
                        "decision", "change", "list", "timeline", "location",
                        "snapshot", "confirm", "impact", "validate", "render",
                        "archive", "restore"):
            self.assertIn(command, result.stdout)

    def _init_project(self, root):
        result = subprocess.run(
            [
                sys.executable, str(SCRIPT), "init",
                "--root", str(root),
                "--name", "Story",
                "--script-master", "markdown",
                "--interaction-profile", "balanced",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_timeline_add_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            self._init_project(root)
            payload_path = Path(tmp) / "timeline.json"
            payload_path.write_text(json.dumps({
                "event_id": "EVT-0001",
                "time_kind": "relative",
                "relation": "before",
                "anchor": "EVT-0002",
                "precision": "unknown",
                "status": "pending",
                "source_refs": ["SRC-0001"],
                "known_by": ["CHR-0001"],
            }, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "timeline", "add",
                    "--root", str(root),
                    "--event-id", "EVT-0001",
                    "--json", str(payload_path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = (root / "store" / "timeline.jsonl").read_text("utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["event_id"], "EVT-0001")

    def test_location_state_command(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            self._init_project(root)
            payload_path = Path(tmp) / "location.json"
            payload_path.write_text(json.dumps({
                "location_id": "LOC-0001",
                "valid_from": "760-01-01",
                "valid_to": None,
                "controller": "FCT-0001",
                "status": "正常",
                "precision": "approximate",
                "roads": [],
                "resources": [],
                "events": [],
            }, ensure_ascii=False), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT), "location", "state",
                    "--root", str(root),
                    "--location-id", "LOC-0001",
                    "--json", str(payload_path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            lines = (root / "store" / "location_states.jsonl").read_text("utf-8").splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["location_id"], "LOC-0001")


if __name__ == "__main__":
    unittest.main()
