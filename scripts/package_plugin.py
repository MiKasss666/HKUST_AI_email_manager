"""Build the installable .difypkg package for the Email Manager plugin.

    py -3 scripts/package_plugin.py

The .difypkg is a zip whose root contains manifest.yaml, main.py, provider/,
tools/, lib/ ...  Zip entry names must use forward slashes (the Dify plugin
daemon is written in Go and treats backslashes as part of the file name).
"""

from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugin" / "email_manager"
OUTPUT = ROOT / "build" / "email_manager.difypkg"
EXCLUDE_DIRS = {"__pycache__", "tests"}


def main() -> int:
    if not (PLUGIN / "manifest.yaml").exists():
        print("manifest.yaml not found under", PLUGIN)
        return 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()

    count = 0
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(PLUGIN.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(PLUGIN)
            if any(part in EXCLUDE_DIRS for part in relative.parts):
                continue
            if path.name.endswith(".pyc") or path.name == ".difyignore":
                continue
            archive.write(path, arcname=relative.as_posix())
            count += 1

    size = OUTPUT.stat().st_size
    print("built: %s (%d files, %.1f KB)" % (OUTPUT, count, size / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
