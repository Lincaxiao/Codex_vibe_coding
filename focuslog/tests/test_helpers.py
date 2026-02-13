from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
import uuid


@contextmanager
def local_tmp_dir():
    base = Path(__file__).resolve().parent / "_tmp"
    base.mkdir(parents=True, exist_ok=True)
    for child in base.iterdir():
        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
    path = base / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=False)
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)
