"""Install a ch-write-skill source tree into a target directory.

The installer intentionally refuses to overwrite or merge into an existing
target directory: ``shutil.copytree`` raises ``FileExistsError`` when the
destination already exists.  After copying, relative file digests are compared
so a partial or divergent copy fails loudly with ``RuntimeError``.
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path


def _digest_tree(root: Path) -> dict[str, str]:
    """Return a SHA-256 digest for every regular file under *root*.

    ``__pycache__`` directories are intentionally skipped, matching the
    copy filter and keeping the digest comparison independent of local
    bytecode caches.
    """
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts:
            rel = path.relative_to(root).as_posix()
            result[rel] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def install_skill(source: Path, target: Path) -> None:
    """Copy *source* to *target* and verify the copy is identical.

    Raises:
        FileNotFoundError: if *source* does not exist.
        FileExistsError: if *target* already exists (no overwrite).
        RuntimeError: if the copied tree differs from the source tree.
    """
    source = Path(source)
    target = Path(target)

    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns("__pycache__"),
    )

    source_digest = _digest_tree(source)
    target_digest = _digest_tree(target)
    if source_digest != target_digest:
        raise RuntimeError(
            "installed skill differs from source: "
            f"source={source}, target={target}"
        )
