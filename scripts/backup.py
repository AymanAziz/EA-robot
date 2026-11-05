#!/usr/bin/env python3
"""Consistent SQLite online backups; stop writers first for a cross-database snapshot."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import shutil
import sqlite3


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path("var"))
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    destination = args.destination / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination.mkdir(parents=True, mode=0o700)
    databases = sorted(set(args.state_dir.glob("*.db")) | set(args.state_dir.glob("*.sqlite*")))
    databases = [path for path in databases if not path.name.endswith(("-shm", "-wal", "-journal"))]
    if not databases:
        raise SystemExit("No database files found; nothing was backed up.")
    for source in databases:
        with sqlite3.connect(f"file:{source.resolve()}?mode=ro", uri=True) as current:
            with sqlite3.connect(destination / source.name) as backup:
                current.backup(backup)
                if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise SystemExit("Backup integrity check failed.")
    models = args.state_dir / "models"
    if models.exists():
        shutil.copytree(models, destination / "models")
    print(f"Verified backup: {destination}")


if __name__ == "__main__":
    main()
