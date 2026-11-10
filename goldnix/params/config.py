"""Strict YAML loading for research configuration."""

from __future__ import annotations

from pathlib import Path

import yaml


class _StrictLoader(yaml.SafeLoader):
    """Safe YAML loader that accepts only explicit true/false booleans."""


def _construct_strict_boolean(loader: _StrictLoader, node: yaml.nodes.ScalarNode) -> bool:
    value = loader.construct_scalar(node)
    if value.lower() not in {"true", "false"}:
        raise ValueError(f"ambiguous YAML boolean {value!r}; use true/false or quote the value")
    return value.lower() == "true"


_StrictLoader.add_constructor("tag:yaml.org,2002:bool", _construct_strict_boolean)


def load_yaml(path: str | Path):
    """Load YAML safely while rejecting YAML 1.1's ambiguous boolean words."""
    with Path(path).open(encoding="utf-8") as source:
        return yaml.load(source, Loader=_StrictLoader)


def dump_yaml(data, path: str | Path) -> None:
    """Write configuration using unambiguous safe YAML values."""
    with Path(path).open("w", encoding="utf-8") as target:
        yaml.safe_dump(data, target, sort_keys=False)
