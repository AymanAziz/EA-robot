from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "backup.py"
GENERATION = re.compile(r"^\d{8}T\d{6}Z$")


def database(path: Path, value: str = "preserved", *, wal: bool = False) -> None:
    with sqlite3.connect(path) as connection:
        if wal:
            assert connection.execute("pragma journal_mode=wal").fetchone()[0] == "wal"
        connection.execute("create table evidence (value text not null)")
        connection.execute("insert into evidence values (?)", (value,))


def run_backup(state: Path, destination: Path, keep: int = 7, *,
               rotate_logs: bool = False, max_log_bytes: int = 1024,
               log_generations: int = 3) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable, str(SCRIPT), "--state-dir", str(state),
        "--destination", str(destination), "--keep", str(keep),
    ]
    if rotate_logs:
        command.extend(["--rotate-launchd-logs", "--max-log-bytes", str(max_log_bytes),
                        "--log-generations", str(log_generations)])
    return subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)


def recognized_generation(path: Path) -> None:
    path.mkdir()
    database(path / "papertrade.db")
    copied = path / "papertrade.db"
    manifest = {"schema_version": 1, "generation": path.name, "files": [{
        "path": copied.name, "bytes": copied.stat().st_size,
        "sha256": hashlib.sha256(copied.read_bytes()).hexdigest(),
    }]}
    (path / "manifest.json").write_text(json.dumps(manifest))


def test_backup_is_verified_manifested_and_records_atomic_success(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    database(state / "papertrade.db", wal=True)
    database(state / "simulator.db", "paper-only", wal=True)
    model = state / "models" / "BTC_USD" / "candidate" / "booster.txt"
    model.parent.mkdir(parents=True)
    model.write_text("tree\n")
    destination = state / "daily-backups"

    result = run_backup(state, destination)

    assert result.returncode == 0, result.stderr
    generations = [path for path in destination.iterdir() if GENERATION.fullmatch(path.name)]
    assert len(generations) == 1
    generation = generations[0]
    manifest = json.loads((generation / "manifest.json").read_text())
    assert manifest["schema_version"] == 1
    assert manifest["generation"] == generation.name
    entries = {entry["path"]: entry for entry in manifest["files"]}
    assert set(entries) == {"papertrade.db", "simulator.db", "models/BTC_USD/candidate/booster.txt"}
    assert not list(generation.glob("*.db-wal"))
    assert not list(generation.glob("*.db-shm"))
    for relative, entry in entries.items():
        copied = generation / relative
        assert copied.stat().st_size == entry["bytes"]
        assert hashlib.sha256(copied.read_bytes()).hexdigest() == entry["sha256"]
    with sqlite3.connect(generation / "papertrade.db") as connection:
        assert connection.execute("pragma integrity_check").fetchone()[0] == "ok"
        assert connection.execute("select value from evidence").fetchone()[0] == "preserved"
    status_path = state / "backup-status.json"
    status = json.loads(status_path.read_text())
    assert status == {"schema_version": 1, "status": "ok", "generation": generation.name,
                      "retained_generations": 1}
    assert status_path.stat().st_mode & 0o777 == 0o600
    assert not list(state.glob(".backup-status.*.tmp"))
    assert not list(destination.glob(".*.tmp"))


def test_retention_runs_only_after_verified_publish_and_ignores_unrecognized_paths(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    database(state / "papertrade.db")
    destination = state / "daily-backups"
    destination.mkdir()
    old = destination / "20240101T000000Z"
    recent = destination / "20240102T000000Z"
    recognized_generation(old)
    recognized_generation(recent)
    unrelated = destination / "20200101T000000Z-not-a-backup"
    unrelated.mkdir()
    (destination / "operator-notes.txt").write_text("keep")

    result = run_backup(state, destination, keep=2)

    assert result.returncode == 0, result.stderr
    retained = sorted(path.name for path in destination.iterdir() if GENERATION.fullmatch(path.name))
    assert len(retained) == 2
    assert old.name not in retained
    assert recent.name in retained
    assert unrelated.is_dir()
    assert (destination / "operator-notes.txt").read_text() == "keep"


def test_retention_never_deletes_a_generation_with_unmanifested_content(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    database(state / "papertrade.db")
    destination = state / "daily-backups"
    destination.mkdir()
    protected = destination / "20240101T000000Z"
    recognized_generation(protected)
    note = protected / "operator-note.txt"
    note.write_text("must survive retention")
    pruneable = destination / "20240102T000000Z"
    recognized_generation(pruneable)

    result = run_backup(state, destination, keep=1)

    assert result.returncode == 0, result.stderr
    assert note.read_text() == "must survive retention"
    assert protected.is_dir()
    assert not pruneable.exists()


def test_retention_never_treats_manifested_sqlite_sidecars_as_restore_ready(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    database(state / "papertrade.db")
    destination = state / "daily-backups"
    destination.mkdir()
    protected = destination / "20240101T000000Z"
    recognized_generation(protected)
    sidecar = protected / "papertrade.db-wal"
    sidecar.write_bytes(b"")
    manifest_path = protected / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"].append({"path": sidecar.name, "bytes": 0,
                              "sha256": hashlib.sha256(b"").hexdigest()})
    manifest_path.write_text(json.dumps(manifest))
    pruneable = destination / "20240102T000000Z"
    recognized_generation(pruneable)

    result = run_backup(state, destination, keep=1)

    assert result.returncode == 0, result.stderr
    assert protected.is_dir() and sidecar.is_file()
    assert not pruneable.exists()


def test_failed_verification_never_prunes_and_records_non_secret_failure(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "papertrade.db").write_bytes(b"not sqlite")
    destination = state / "daily-backups"
    destination.mkdir()
    originals = [destination / f"2024010{day}T000000Z" for day in range(1, 4)]
    for path in originals:
        recognized_generation(path)

    result = run_backup(state, destination, keep=1)

    assert result.returncode != 0
    assert all(path.is_dir() for path in originals)
    assert not list(destination.glob(".*.tmp"))
    status = json.loads((state / "backup-status.json").read_text())
    assert status["schema_version"] == 1
    assert status["status"] == "error"
    assert set(status) == {"schema_version", "status", "error_type"}
    assert str(state) not in json.dumps(status)


def test_unsafe_destination_and_retention_are_rejected_without_deleting_state(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    database(state / "papertrade.db")

    same_directory = run_backup(state, state)
    ancestor = run_backup(state, tmp_path)
    invalid_keep = run_backup(state, state / "daily-backups", keep=0)

    assert same_directory.returncode != 0
    assert ancestor.returncode != 0
    assert invalid_keep.returncode != 0
    assert (state / "papertrade.db").is_file()
    assert not (state / "manifest.json").exists()


def test_launchd_log_rotation_is_bounded_to_direct_matching_files_and_preserves_active_inode(tmp_path):
    state = tmp_path / "state"
    state.mkdir()
    database(state / "papertrade.db")
    active = state / "scheduler-launchd.log"
    current = b"x" * (1024 * 1024 + 1)
    active.write_bytes(current)
    original_inode = active.stat().st_ino
    (state / "scheduler-launchd.log.1").write_bytes(b"previous\n")
    (state / "scheduler-launchd.log.2").write_bytes(b"oldest\n")
    unrelated = state / "application.log"
    unrelated.write_bytes(b"unrelated\n" * 10)
    nested = state / "nested"
    nested.mkdir()
    (nested / "other-launchd.log").write_bytes(b"nested\n" * 10)

    result = run_backup(state, state / "daily-backups", rotate_logs=True,
                        max_log_bytes=1024 * 1024, log_generations=2)

    assert result.returncode == 0, result.stderr
    assert active.is_file() and active.stat().st_ino == original_inode
    assert active.read_bytes() == b""
    assert (state / "scheduler-launchd.log.1").read_bytes() == current
    assert (state / "scheduler-launchd.log.2").read_bytes() == b"previous\n"
    assert not (state / "scheduler-launchd.log.3").exists()
    assert unrelated.read_bytes() == b"unrelated\n" * 10
    assert (nested / "other-launchd.log").read_bytes() == b"nested\n" * 10
