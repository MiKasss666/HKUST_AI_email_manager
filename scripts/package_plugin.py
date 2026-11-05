"""Build the installable .difypkg package for the Email Manager plugin.

    py -3 scripts/package_plugin.py

The plugin source now lives at the repository root (Dify's "Install from
GitHub" requires manifest.yaml at the repo root), so only the plugin files are
packed and documentation/scripts/workflow files are skipped.

Zip entry names must use forward slashes (the Dify plugin daemon is written in
Go and treats backslashes as part of the file name).
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "build" / "email_manager.difypkg"

# plugin files / directories to include (relative to the repository root)
INCLUDE_FILES = ["manifest.yaml", "main.py", "requirements.txt", "PRIVACY.md"]
INCLUDE_DIRS = ["provider", "tools", "lib", "_assets"]
SKIP_NAMES = {"__pycache__", ".DS_Store"}
SKIP_SUFFIXES = (".pyc", ".pyo")


def iter_files():
    for name in INCLUDE_FILES:
        path = ROOT / name
        if path.is_file():
            yield path
    for directory in INCLUDE_DIRS:
        base = ROOT / directory
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                yield path


def main() -> int:
    if not (ROOT / "manifest.yaml").exists():
        print("manifest.yaml not found at", ROOT)
        return 1
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists():
        OUTPUT.unlink()

    count = 0
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in iter_files():
            relative = path.relative_to(ROOT)
            if any(part in SKIP_NAMES for part in relative.parts):
                continue
            if path.name.endswith(SKIP_SUFFIXES):
                continue
            archive.write(path, arcname=relative.as_posix())
            count += 1

    size = OUTPUT.stat().st_size
    print("built: %s (%d files, %.1f KB)" % (OUTPUT, count, size / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
