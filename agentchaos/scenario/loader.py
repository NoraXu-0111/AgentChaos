"""YAML scenario loader and stable hash."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agentchaos.scenario.schema import Scenario


class LoaderError(Exception):
    """Raised when a scenario file cannot be loaded or validated."""


_ENV_PATTERN = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)\}")


def _expand_env(value: Any) -> Any:
    """Expand ${ENV_VAR} references inside string values. Missing vars stay literal."""
    if isinstance(value, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), m.group(0)), value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value


def load_scenario(path: str | Path) -> Scenario:
    """Load and validate a scenario YAML file.

    Raises ``LoaderError`` with a human-readable message on any failure.
    """
    p = Path(path)
    if not p.exists():
        raise LoaderError(f"scenario file not found: {p}")
    try:
        raw = yaml.safe_load(p.read_text())
    except yaml.YAMLError as exc:
        raise LoaderError(f"{p}: invalid YAML — {exc}") from exc
    if raw is None:
        raise LoaderError(f"{p}: scenario file is empty")
    if not isinstance(raw, dict):
        raise LoaderError(f"{p}: top-level must be a mapping")

    expanded = _expand_env(raw)
    try:
        return Scenario.model_validate(expanded)
    except ValidationError as exc:
        first = exc.errors()[0]
        loc = ".".join(str(x) for x in first.get("loc", ()))
        msg = first.get("msg", "validation error")
        raise LoaderError(f"{p}: {loc}: {msg}") from exc


def scenario_hash(scenario: Scenario) -> str:
    """Stable SHA-256 of the scenario *definition*.

    Excludes ``metadata`` (treated as runtime context, not identity).
    Stable across whitespace and key-order changes.
    """
    payload = scenario.model_dump(mode="json", exclude={"metadata"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
