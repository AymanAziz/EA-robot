"""Immutable config/code freeze and holdout access guard."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from params.config import dump_yaml, load_yaml

_CODE_SUFFIXES = {".py", ".mq5", ".yaml", ".ini"}
_EXCLUDED_TOP_LEVEL = {"out", "data"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def research_code_hash(root: str | Path) -> str:
    """Hash research source and tests while excluding data and generated output."""
    root = Path(root)
    digest = hashlib.sha256()
    files = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix not in _CODE_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if relative.parts[0] in _EXCLUDED_TOP_LEVEL or "__pycache__" in relative.parts:
            continue
        files.append((relative, path))
    for relative, path in sorted(files, key=lambda item: item[0].as_posix()):
        digest.update(relative.as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def write_freeze(
    root: str | Path,
    *,
    code_commit: str,
    verdict: str,
) -> Path:
    """Write the immutable decision snapshot after the in-sample verdict."""
    root = Path(root)
    config_path = root / "params" / "decision.yaml"
    target = root / "out" / "FROZEN.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "decision_config": load_yaml(config_path),
        "decision_config_sha256": _sha256(config_path),
        "research_code_sha256": research_code_hash(root),
        "code_commit": code_commit,
        "in_sample_verdict": verdict,
        "created_utc": datetime.now(UTC).isoformat(),
    }
    dump_yaml(payload, target)
    return target


def verify_freeze(root: str | Path) -> bool:
    """Return whether current decision config and research code match the freeze."""
    root = Path(root)
    frozen_path = root / "out" / "FROZEN.yaml"
    if not frozen_path.exists():
        return False
    frozen = load_yaml(frozen_path)
    config_path = root / "params" / "decision.yaml"
    return (
        frozen.get("decision_config_sha256") == _sha256(config_path)
        and frozen.get("research_code_sha256") == research_code_hash(root)
    )


def assert_holdout_unlocked(root: str | Path) -> None:
    """Refuse holdout access until the exact config and code are frozen."""
    root = Path(root)
    frozen_path = root / "out" / "FROZEN.yaml"
    if not frozen_path.exists():
        raise PermissionError("holdout locked: out/FROZEN.yaml does not exist")
    if not verify_freeze(root):
        raise PermissionError("holdout locked: frozen config/code hash mismatch")
