"""Tamper-evident snapshots for completed evaluations, including failed verdicts."""

from __future__ import annotations

import hashlib
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import yaml
from params.config import load_yaml


def source_manifest(root):
    root = Path(root)
    files = []
    for directory in ("goldnix", "goldnix_v2", "goldnix_step6"):
        for path in (root / directory).rglob("*"):
            relative = path.relative_to(root / directory)
            if (not path.is_file() or relative.parts[0] in {"data", "out"}
                    or "__pycache__" in relative.parts):
                continue
            if path.suffix in {".py", ".yaml", ".mq5", ".ini", ".md"}:
                files.append(path)
    for name in ("pyproject.toml", "requirements.lock.txt", "goldnix/data/eras.yaml"):
        if (root / name).exists():
            files.append(root / name)
    return {p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(files)}


def assert_sources_committed(root, commit):
    """Require the manifest to match committed blobs; unrelated workspace files are allowed."""
    for relative, digest in source_manifest(root).items():
        result = subprocess.run(["git", "show", f"{commit}:{relative}"], cwd=root,
                                capture_output=True, check=False)
        if result.returncode or hashlib.sha256(result.stdout).hexdigest() != digest:
            raise RuntimeError(f"Uncommitted research source: {relative}")


def freeze_run(root, run, *, verdict, code_commit, configs):
    root, run = Path(root), Path(run)
    artifacts = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                 for p in sorted(run.iterdir()) if p.is_file() and p.name != "FROZEN.yaml"}
    snapshot = {
        "created_utc": datetime.now(UTC).isoformat(), "code_commit": code_commit,
        "evaluation_complete": True, "verdict": verdict,
        "configs": configs, "source_manifest": source_manifest(root),
        "artifact_sha256": artifacts, "holdout_run": False,
    }
    with (run / "FROZEN.yaml").open("x", encoding="utf-8") as handle:
        yaml.safe_dump(snapshot, handle, sort_keys=True)


def verify_run(root, run):
    root, run = Path(root), Path(run)
    frozen = load_yaml(run / "FROZEN.yaml")
    if frozen["source_manifest"] != source_manifest(root):
        return False
    return all((run / name).is_file() and hashlib.sha256((run / name).read_bytes()).hexdigest() == digest
               for name, digest in frozen["artifact_sha256"].items())
