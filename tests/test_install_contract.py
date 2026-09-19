import hashlib
import tempfile
import unittest
from pathlib import Path
from ch_write.install import install_skill

ROOT = Path(__file__).resolve().parents[1]

class TestInstallContract(unittest.TestCase):
    def _digest_tree(self, root: Path) -> dict[str, str]:
        result = {}
        for path in sorted(root.rglob("*")):
            if path.is_file() and "__pycache__" not in path.parts:
                rel = path.relative_to(root).as_posix()
                result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    def test_install_copy_is_identical_and_refuses_existing_target(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "ch-write-skill"
            install_skill(ROOT, target)
            self.assertEqual(self._digest_tree(ROOT), self._digest_tree(target))
            with self.assertRaises(FileExistsError):
                install_skill(ROOT, target)
