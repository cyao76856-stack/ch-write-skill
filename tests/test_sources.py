import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from ch_write.io import read_json
from ch_write.project import init_project
from ch_write.sources import compute_digest, extract_docx_text, register_sources

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "story_project.py"


def write_minimal_docx(path: Path, text: str = "正文") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(
            "word/document.xml",
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
            f'<w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body></w:document>',
        )


class TestSources(unittest.TestCase):
    def test_txt_md_and_docx_registration(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            txt = Path(tmp) / "a.txt"
            txt.write_text("第一幕", encoding="utf-8")
            docx = Path(tmp) / "b.docx"
            write_minimal_docx(docx)
            result = register_sources(root, [
                {"path": str(txt), "order": 1, "priority": 10, "merge_strategy": "primary"},
                {"path": str(docx), "order": 2, "priority": 20, "merge_strategy": "reference"},
            ])
            self.assertEqual(len(result["sources"]), 2)
            self.assertEqual(extract_docx_text(docx), "正文")
            self.assertEqual(result["sources"][0]["digest"], compute_digest(txt))
            self.assertEqual(result["sources"][0]["source_id"], "SRC-0001")
            self.assertEqual(result["sources"][1]["source_id"], "SRC-0002")
            self.assertEqual(read_json(root / "indexes" / "sources.json"), result)

    def test_digest_change_is_detected_not_merged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            src = Path(tmp) / "a.md"
            src.write_text("old", encoding="utf-8")
            original = register_sources(root, [
                {"path": str(src), "order": 1, "priority": 1, "merge_strategy": "primary"}
            ])
            src.write_text("new", encoding="utf-8")
            report = register_sources(root, [], replace=False)
            self.assertEqual(report["sources"][0]["status"], "source-changed")
            self.assertEqual(
                report["sources"][0]["digest"],
                original["sources"][0]["digest"],
            )

    def test_missing_source_is_marked_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            missing = Path(tmp) / "missing.md"
            result = register_sources(root, [
                {"path": str(missing), "order": 1, "priority": 1, "merge_strategy": "primary"}
            ])
            self.assertEqual(result["sources"][0]["status"], "missing")
            self.assertIsNone(result["sources"][0]["digest"])
            self.assertFalse((root / "store" / "sources").exists())

    def test_invalid_docx_raises_value_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.docx"
            path.write_bytes(b"not a zip archive")
            with self.assertRaisesRegex(ValueError, "^invalid DOCX file$"):
                extract_docx_text(path)

    def test_paragraph_text_is_joined_with_newlines(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "two.docx"
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr(
                    "word/document.xml",
                    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                    '<w:body><w:p><w:r><w:t>第一段</w:t></w:r></w:p>'
                    '<w:p><w:r><w:t>第二段</w:t></w:r></w:p></w:body></w:document>',
                )
            self.assertEqual(extract_docx_text(path), "第一段\n第二段")

    def test_replace_updates_digest_without_changing_source_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            src = Path(tmp) / "a.md"
            src.write_text("old", encoding="utf-8")
            original = register_sources(root, [
                {"path": str(src), "order": 1, "priority": 1, "merge_strategy": "primary"}
            ])
            src.write_text("new", encoding="utf-8")
            replaced = register_sources(root, [
                {"path": str(src), "order": 1, "priority": 2, "merge_strategy": "reference"}
            ], replace=True)
            record = replaced["sources"][0]
            self.assertEqual(record["source_id"], original["sources"][0]["source_id"])
            self.assertEqual(record["digest"], compute_digest(src))
            self.assertEqual(record["priority"], 2)
            self.assertEqual(record["merge_strategy"], "reference")
            self.assertEqual(record["status"], "registered")


    def test_repeated_entry_detects_digest_change_without_replacing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            src = Path(tmp) / "a.md"
            src.write_text("old", encoding="utf-8")
            original = register_sources(root, [
                {"path": str(src), "order": 1, "priority": 1, "merge_strategy": "primary"}
            ])
            source_id = original["sources"][0]["source_id"]
            src.write_text("new", encoding="utf-8")

            report = register_sources(root, [
                {
                    "source_id": source_id,
                    "path": str(src),
                    "order": 1,
                    "priority": 2,
                    "merge_strategy": "reference",
                }
            ])
            record = report["sources"][0]
            self.assertEqual(record["status"], "source-changed")
            self.assertEqual(record["digest"], original["sources"][0]["digest"])
            self.assertEqual(record["priority"], 1)


class TestSourceCli(unittest.TestCase):
    def run_cli(self, *args, cwd=None):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=cwd,
        )

    def test_source_add_writes_index_without_copying_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            source = Path(tmp) / "source.txt"
            source.write_text("来源正文", encoding="utf-8")

            result = self.run_cli(
                "source", "add", "--root", str(root), "--file", str(source),
                "--order", "1", "--priority", "5", "--merge-strategy", "primary",
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            index = read_json(root / "indexes" / "sources.json")
            self.assertEqual(index["sources"][0]["source_id"], "SRC-0001")
            self.assertFalse((root / "store" / "sources").exists())

    def test_relative_source_path_survives_working_directory_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / "story"
            first_cwd = base / "first"
            second_cwd = base / "second"
            first_cwd.mkdir()
            second_cwd.mkdir()
            init_project(root, "Story", "markdown", "balanced")
            source = first_cwd / "source.txt"
            source.write_text("source", encoding="utf-8")

            added = self.run_cli(
                "source", "add", "--root", str(root), "--file", "source.txt",
                "--order", "1", "--priority", "5", "--merge-strategy", "primary",
                cwd=first_cwd,
            )
            self.assertEqual(added.returncode, 0, added.stderr)
            expected_path = str(source.resolve())
            registered = read_json(root / "indexes" / "sources.json")["sources"][0]
            self.assertEqual(registered["path"], expected_path)
            self.assertEqual(registered["input_path"], "source.txt")

            status = self.run_cli(
                "source", "status", "--root", str(root), cwd=second_cwd
            )
            self.assertEqual(status.returncode, 0, status.stderr)
            report = json.loads(status.stdout)
            self.assertEqual(len(report["sources"]), 1)
            record = report["sources"][0]
            self.assertEqual(record["status"], "registered")
            self.assertEqual(record["path"], expected_path)
            self.assertEqual(record["input_path"], "source.txt")

    def test_source_add_requires_replace_for_existing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            source = Path(tmp) / "source.txt"
            source.write_text("old", encoding="utf-8")
            arguments = (
                "source", "add", "--root", str(root), "--file", str(source),
                "--order", "1", "--priority", "5", "--merge-strategy", "primary",
            )
            self.assertEqual(self.run_cli(*arguments).returncode, 0)

            duplicate = self.run_cli(*arguments)
            self.assertNotEqual(duplicate.returncode, 0)
            self.assertIn("already registered", duplicate.stderr)

            source.write_text("new", encoding="utf-8")
            replaced = self.run_cli(*arguments, "--replace")
            self.assertEqual(replaced.returncode, 0, replaced.stderr)
            index = read_json(root / "indexes" / "sources.json")
            self.assertEqual(len(index["sources"]), 1)
            self.assertEqual(index["sources"][0]["digest"], compute_digest(source))

    def test_source_status_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            source = Path(tmp) / "source.txt"
            source.write_text("old", encoding="utf-8")
            added = self.run_cli(
                "source", "add", "--root", str(root), "--file", str(source),
                "--order", "1", "--priority", "5", "--merge-strategy", "primary",
            )
            self.assertEqual(added.returncode, 0, added.stderr)
            original = read_json(root / "indexes" / "sources.json")
            old_digest = original["sources"][0]["digest"]
            source.write_text("new", encoding="utf-8")

            status = self.run_cli("source", "status", "--root", str(root))
            self.assertEqual(status.returncode, 0, status.stderr)
            report = json.loads(status.stdout)
            self.assertEqual(report["sources"][0]["status"], "source-changed")
            self.assertEqual(report["sources"][0]["digest"], old_digest)

            persisted = read_json(root / "indexes" / "sources.json")
            self.assertEqual(persisted, original)

    def test_source_status_outputs_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "story"
            init_project(root, "Story", "markdown", "balanced")
            source = Path(tmp) / "source.txt"
            source.write_text("source", encoding="utf-8")
            self.assertEqual(
                self.run_cli(
                    "source", "add", "--root", str(root), "--file", str(source),
                    "--order", "1", "--priority", "5", "--merge-strategy", "primary",
                ).returncode,
                0,
            )

            result = self.run_cli("source", "status", "--root", str(root))

            self.assertEqual(result.returncode, 0, result.stderr)
            status = json.loads(result.stdout)
            self.assertEqual(status["sources"][0]["source_id"], "SRC-0001")


if __name__ == "__main__":
    unittest.main()