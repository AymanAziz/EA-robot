#!/usr/bin/env python3
"""Verified SQLite/model backups with bounded retention and optional launchd-log rotation.

SQLite files are backed up consistently one at a time. Stop all writers when a
single cross-database point-in-time snapshot is required.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import sys


GENERATION = re.compile(r"^\d{8}T\d{6}Z$")
STATUS_NAME = "backup-status.json"


class BackupError(RuntimeError):
    pass


def _positive(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= 365:
        raise argparse.ArgumentTypeError("value must be between 1 and 365")
    return parsed


def _byte_count(value: str) -> int:
    parsed = int(value)
    if not 1 <= parsed <= 1024 * 1024 * 1024:
        raise argparse.ArgumentTypeError("byte count must be between 1 and 1073741824")
    return parsed


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
        temporary.chmod(0o600)
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _paths(state_dir: Path, destination: Path) -> tuple[Path, Path]:
    if state_dir.is_symlink() or not state_dir.is_dir():
        raise BackupError("State directory must be an existing real directory")
    state = state_dir.resolve(strict=True)
    if destination.is_symlink():
        raise BackupError("Backup destination cannot be a symbolic link")
    target = destination.resolve(strict=False)
    root = Path(target.anchor)
    if target in {root, state} or state.is_relative_to(target):
        raise BackupError("Backup destination is too broad")
    if target.exists() and not target.is_dir():
        raise BackupError("Backup destination must be a directory")
    target.mkdir(parents=True, mode=0o700, exist_ok=True)
    target.chmod(0o700)
    return state, target


def _source_databases(state: Path) -> list[Path]:
    candidates = sorted(set(state.glob("*.db")) | set(state.glob("*.sqlite*")))
    result = []
    for path in candidates:
        if path.name.endswith(("-shm", "-wal", "-journal")):
            continue
        if path.is_symlink() or not path.is_file() or path.resolve().parent != state:
            raise BackupError("Database sources must be regular files directly inside state")
        result.append(path)
    if not result:
        raise BackupError("No database files found")
    return result


def _copy_database(source: Path, destination: Path) -> None:
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as current:
        with sqlite3.connect(destination) as backup:
            current.backup(backup)
            if backup.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("Backup integrity check failed")
            # A source in WAL mode transfers that persistent journal setting.
            # Publish one standalone database file, never recovery sidecars.
            journal = backup.execute("PRAGMA journal_mode=DELETE").fetchone()[0]
            if str(journal).lower() != "delete":
                raise BackupError("Backup journal normalization failed")
    destination.chmod(0o600)


def _safe_models(state: Path) -> Path | None:
    models = state / "models"
    if not models.exists():
        return None
    if models.is_symlink() or not models.is_dir():
        raise BackupError("Models must be a real directory")
    if any(path.is_symlink() for path in models.rglob("*")):
        raise BackupError("Model backups do not follow symbolic links")
    return models


def _manifest(generation: Path, published_name: str) -> dict:
    files = []
    for path in sorted(candidate for candidate in generation.rglob("*")
                       if candidate.is_file() and candidate.name != "manifest.json"):
        if path.is_symlink():
            raise BackupError("Backup generations cannot contain symbolic links")
        files.append({"path": path.relative_to(generation).as_posix(),
                      "bytes": path.stat().st_size, "sha256": _sha256(path)})
    return {"schema_version": 1, "generation": published_name,
            "created_at": datetime.now(timezone.utc).isoformat(), "files": files}


def _verify_generation(generation: Path) -> bool:
    try:
        if generation.is_symlink() or not generation.is_dir() or not GENERATION.fullmatch(generation.name):
            return False
        manifest_path = generation / "manifest.json"
        if manifest_path.is_symlink() or not manifest_path.is_file():
            return False
        manifest = json.loads(manifest_path.read_text())
        if (manifest.get("schema_version") != 1 or manifest.get("generation") != generation.name
                or not isinstance(manifest.get("files"), list) or not manifest["files"]):
            return False
        database_found = False
        seen = set()
        expected_files = {"manifest.json"}
        expected_directories = set()
        for entry in manifest["files"]:
            relative = Path(entry["path"])
            normalized = relative.as_posix()
            if (relative.is_absolute() or ".." in relative.parts or normalized in seen
                    or normalized == "manifest.json"
                    or relative.name.endswith(("-wal", "-shm", "-journal"))):
                return False
            seen.add(normalized)
            expected_files.add(normalized)
            parent = relative.parent
            while parent != Path("."):
                expected_directories.add(parent.as_posix())
                parent = parent.parent
            path = generation / relative
            if (path.is_symlink() or not path.is_file() or path.stat().st_size != entry["bytes"]
                    or _sha256(path) != entry["sha256"]):
                return False
            if relative.parent == Path(".") and (relative.suffix == ".db" or ".sqlite" in relative.name):
                database_found = True
                with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
                    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        return False
        actual_files = set()
        actual_directories = set()
        for path in generation.rglob("*"):
            if path.is_symlink() or not (path.is_file() or path.is_dir()):
                return False
            relative = path.relative_to(generation).as_posix()
            if path.is_file():
                actual_files.add(relative)
            else:
                actual_directories.add(relative)
        return (database_found and actual_files == expected_files
                and actual_directories == expected_directories)
    except (KeyError, TypeError, ValueError, OSError, sqlite3.DatabaseError, json.JSONDecodeError):
        return False


def _prune(destination: Path, keep: int) -> int:
    verified = sorted(path for path in destination.iterdir() if _verify_generation(path))
    for path in verified[:-keep]:
        if path.parent != destination or path.is_symlink():
            raise BackupError("Refusing unsafe retention target")
        shutil.rmtree(path)
    return len(verified[-keep:])


def _create_backup(state: Path, destination: Path, keep: int) -> tuple[Path, int]:
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final = destination / name
    staging = destination / f".{name}.{os.getpid()}.tmp"
    if final.exists() or staging.exists():
        raise BackupError("Backup generation already exists")
    staging.mkdir(mode=0o700)
    try:
        for source in _source_databases(state):
            _copy_database(source, staging / source.name)
        models = _safe_models(state)
        if models is not None:
            shutil.copytree(models, staging / "models")
        _atomic_json(staging / "manifest.json", _manifest(staging, name))
        staging.rename(final)
        try:
            if not _verify_generation(final):
                raise BackupError("Published backup verification failed")
        except Exception:
            final.rename(staging)
            raise
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise
    retained = _prune(destination, keep)
    return final, retained


def _rotate_launchd_logs(state: Path, maximum_bytes: int, generations: int) -> int:
    rotated = 0
    for active in sorted(state.glob("*-launchd.log")):
        if active.parent != state or active.is_symlink() or not active.is_file():
            continue
        if active.stat().st_size <= maximum_bytes:
            continue
        paths = [Path(f"{active}.{number}") for number in range(1, generations + 1)]
        if any(path.is_symlink() or (path.exists() and not path.is_file()) for path in paths):
            raise BackupError("Refusing unsafe log rotation target")
        temporary = state / f".{active.name}.rotate.{os.getpid()}.tmp"
        try:
            shutil.copyfile(active, temporary)
            temporary.chmod(0o600)
            paths[-1].unlink(missing_ok=True)
            for index in range(generations - 1, 0, -1):
                older, newer = paths[index - 1], paths[index]
                if older.exists():
                    os.replace(older, newer)
            os.replace(temporary, paths[0])
            # Copy-and-truncate preserves the inode held open by launchd children.
            with active.open("r+b") as handle:
                handle.truncate(0)
            rotated += 1
        finally:
            temporary.unlink(missing_ok=True)
    return rotated


def main() -> None:
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path("var"))
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--keep", type=_positive, default=7,
                        help="Number of verified generations to retain (default: 7)")
    parser.add_argument("--rotate-launchd-logs", action="store_true")
    parser.add_argument("--max-log-bytes", type=_byte_count, default=5 * 1024 * 1024)
    parser.add_argument("--log-generations", type=_positive, default=3)
    args = parser.parse_args()
    state_for_status = args.state_dir.expanduser()
    try:
        state, destination = _paths(state_for_status, args.destination.expanduser())
        generation, retained = _create_backup(state, destination, args.keep)
        rotated = (_rotate_launchd_logs(state, args.max_log_bytes, args.log_generations)
                   if args.rotate_launchd_logs else 0)
        status = {"schema_version": 1, "status": "ok", "generation": generation.name,
                  "retained_generations": retained}
        if args.rotate_launchd_logs:
            status["rotated_logs"] = rotated
        _atomic_json(state / STATUS_NAME, status)
        print(f"Verified backup: {generation}")
    except Exception as exc:
        try:
            if state_for_status.is_dir() and not state_for_status.is_symlink():
                _atomic_json(state_for_status / STATUS_NAME, {
                    "schema_version": 1, "status": "error", "error_type": type(exc).__name__})
        except OSError:
            pass
        print(f"Backup failed: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
