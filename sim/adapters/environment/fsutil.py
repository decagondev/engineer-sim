"""Filesystem helpers shared by the sandbox environments."""
from __future__ import annotations

import os
import shutil
import stat
import time
from pathlib import Path


def remove_tree(path: str | os.PathLike, attempts: int = 3) -> bool:
    """Delete a directory tree, including read-only entries (git objects on
    Windows are read-only, which makes a plain rmtree leave the tree behind).
    Returns True when nothing is left at `path`."""
    p = Path(path)
    if not p.exists():
        return True

    def _clear_readonly(func, target, _exc):
        try:
            os.chmod(target, stat.S_IWRITE | stat.S_IREAD)
        except OSError:
            return
        try:
            func(target)
        except OSError:
            pass

    for i in range(attempts):
        try:
            shutil.rmtree(p, onerror=_clear_readonly)
        except OSError:
            pass
        if not p.exists():
            return True
        time.sleep(0.05 * (i + 1))          # a handle closing on Windows
    return not p.exists()
