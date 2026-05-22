"""Rule-based cause detection.

Each rule is a pure function that takes ``(b_trace, c_trace, diff)`` and
returns zero or more :class:`PossibleCause`. The framework deliberately avoids
claiming causation in language — only ``computed`` causes (e.g. model swap with
known prices) make a hard $ claim. Everything else is "Possible contributor"
or "correlates with."
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Literal

from pydantic import BaseModel, ConfigDict

from agentchaos.profile.compare import Diff
from agentchaos.trace.schema import ModelCall, ToolCall, TraceEvent

ConfidenceLevel = Literal["observed", "correlates", "computed"]

_GROWTH_PCT_THRESHOLD = 20.0  # any tracked metric growing more than this is reported
_REPEAT_THRESHOLD = 3  # same args_hash this many times = repeated tool args
_TOKEN_DELTA_PCT_THRESHOLD = 20.0
_PER_MODEL_COST_PCT_THRESHOLD = 20.0


class PossibleCause(BaseModel):
    """One observation, contribution, or correlation that may explain a regression."""

    model_config = ConfigDict(extra="forbid")

    description: str
    correlates_with: list[str]
    confidence: ConfidenceLevel
    contribution_usd: float | None = None


def find_causes(
    baseline_trace: list[TraceEvent],
    candidate_trace: list[TraceEvent],
    diff: Diff,
) -> list[PossibleCause]:
    """Run all rules and return causes ordered by magnitude of contribution."""
    causes: list[PossibleCause] = []
    causes.extend(_rule_input_tokens_grew(diff))
    causes.extend(_rule_output_tokens_grew(diff))
    causes.extend(_rule_llm_call_count_grew(diff))
    causes.extend(_rule_tool_call_count_grew(diff))
    causes.extend(_rule_retry_count_grew(diff))
    causes.extend(_rule_per_model_cost_grew(diff))
    causes.extend(_rule_model_swapped(diff))
    causes.extend(_rule_repeated_tool_args(candidate_trace, baseline_trace))
    causes.extend(_rule_metadata_changed(baseline_trace, candidate_trace))
    return _order(causes)


def _delta(diff: Diff, name: str) -> tuple[float | int | None, float | None]:
    for d in diff.deltas:
        if d.name == name:
            return d.delta_abs, d.delta_pct
    return None, None


def _rule_input_tokens_grew(diff: Diff) -> list[PossibleCause]:
    abs_d, pct = _delta(diff, "total_input_tokens")
    if pct is None or pct <= _TOKEN_DELTA_PCT_THRESHOLD:
        return []
    return [
        PossibleCause(
            description=f"input_tokens grew {pct:+.1f}% ({abs_d:+} tokens)",
            correlates_with=["total_cost_usd"],
            confidence="observed",
        )
    ]


def _rule_output_tokens_grew(diff: Diff) -> list[PossibleCause]:
    abs_d, pct = _delta(diff, "total_output_tokens")
    if pct is None or pct <= _TOKEN_DELTA_PCT_THRESHOLD:
        return []
    return [
        PossibleCause(
            description=f"output_tokens grew {pct:+.1f}% ({abs_d:+} tokens)",
            correlates_with=["total_cost_usd"],
            confidence="observed",
        )
    ]


def _rule_tool_call_count_grew(diff: Diff) -> list[PossibleCause]:
    abs_d, _ = _delta(diff, "tool_calls")
    if abs_d is None or abs_d <= 0:
        return []
    return [
        PossibleCause(
            description=f"tool_calls increased by {abs_d:+}",
            correlates_with=["total_cost_usd", "total_latency_ms"],
            confidence="observed",
        )
    ]


def _rule_llm_call_count_grew(diff: Diff) -> list[PossibleCause]:
    abs_d, _ = _delta(diff, "llm_calls")
    if abs_d is None or abs_d <= 0:
        return []
    return [
        PossibleCause(
            description=f"llm_calls increased by {abs_d:+}",
            correlates_with=["total_cost_usd"],
            confidence="observed",
        )
    ]


def _rule_retry_count_grew(diff: Diff) -> list[PossibleCause]:
    abs_d, _ = _delta(diff, "retries")
    if abs_d is None or abs_d <= 0:
        return []
    return [
        PossibleCause(
            description=f"retries increased by {abs_d:+}",
            correlates_with=["total_cost_usd", "total_latency_ms"],
            confidence="observed",
        )
    ]


def _rule_per_model_cost_grew(diff: Diff) -> list[PossibleCause]:
    out: list[PossibleCause] = []
    for model, c_cost in diff.by_model_candidate.items():
        b_cost = diff.by_model_baseline.get(model, 0.0)
        if b_cost == 0:
            continue
        pct = ((c_cost - b_cost) / b_cost) * 100.0
        if pct > _PER_MODEL_COST_PCT_THRESHOLD:
            out.append(
                PossibleCause(
                    description=(
                        f"per-model cost grew on {model}: "
                        f"${b_cost:.6f} → ${c_cost:.6f} ({pct:+.1f}%)"
                    ),
                    correlates_with=["total_cost_usd"],
                    confidence="observed",
                )
            )
    return out


def _rule_model_swapped(diff: Diff) -> list[PossibleCause]:
    b_models = set(diff.by_model_baseline)
    c_models = set(diff.by_model_candidate)
    if b_models == c_models:
        return []
    added = c_models - b_models
    removed = b_models - c_models
    if not added or not removed:
        return []
    # Compute contribution_usd as the candidate spend on the new model(s).
    contribution_usd = sum(diff.by_model_candidate.get(m, 0.0) for m in added)
    return [
        PossibleCause(
            description=(
                f"model swap detected: {sorted(removed)} → {sorted(added)} "
                f"(${contribution_usd:.6f} on new model"
                + ("s" if len(added) > 1 else "")
                + ")"
            ),
            correlates_with=["total_cost_usd"],
            confidence="computed",
            contribution_usd=contribution_usd,
        )
    ]


def _rule_repeated_tool_args(
    candidate_trace: list[TraceEvent],
    baseline_trace: list[TraceEvent],
) -> list[PossibleCause]:
    cand_signatures: Counter[tuple[str, str]] = Counter()
    base_signatures: Counter[tuple[str, str]] = Counter()
    for ev in candidate_trace:
        if isinstance(ev, ToolCall):
            cand_signatures[(ev.name, ev.args_hash)] += 1
    for ev in baseline_trace:
        if isinstance(ev, ToolCall):
            base_signatures[(ev.name, ev.args_hash)] += 1
    out: list[PossibleCause] = []
    for sig, count in cand_signatures.items():
        if count >= _REPEAT_THRESHOLD and base_signatures.get(sig, 0) < _REPEAT_THRESHOLD:
            name, _ = sig
            out.append(
                PossibleCause(
                    description=(
                        f"{name} called {count}x with identical args_hash "
                        f"(baseline: {base_signatures.get(sig, 0)}x)"
                    ),
                    correlates_with=["tool_calls", "total_cost_usd"],
                    confidence="correlates",
                )
            )
    return out


def _rule_metadata_changed(
    baseline_trace: list[TraceEvent],
    candidate_trace: list[TraceEvent],
) -> list[PossibleCause]:
    b_meta = _model_call_metadata(baseline_trace)
    c_meta = _model_call_metadata(candidate_trace)

    diffs: dict[
        tuple[int, str],
        list[tuple[str, str | int | float | None, str | int | float | None]],
    ] = defaultdict(list)
    keys = set(b_meta) | set(c_meta)
    for key in keys:
        b_dict = b_meta.get(key, {})
        c_dict = c_meta.get(key, {})
        all_fields = set(b_dict) | set(c_dict)
        for field in all_fields:
            b_v = b_dict.get(field)
            c_v = c_dict.get(field)
            if b_v != c_v:
                diffs[key].append((field, b_v, c_v))

    out: list[PossibleCause] = []
    for (turn_idx, name), changes in diffs.items():
        for field, b_v, c_v in changes:
            label = f"{name} (turn {turn_idx})" if name else f"turn {turn_idx}"
            out.append(
                PossibleCause(
                    description=(
                        f"metadata.{field} changed on model_call {label}: {b_v} → {c_v}"
                    ),
                    correlates_with=["total_input_tokens", "total_cost_usd"],
                    confidence="correlates",
                )
            )
    return out


def _model_call_metadata(
    trace: list[TraceEvent],
) -> dict[tuple[int, str], dict[str, str | int | float | None]]:
    """Index model_call metadata by (turn_index, name)."""
    out: dict[tuple[int, str], dict[str, str | int | float | None]] = {}
    for ev in trace:
        if isinstance(ev, ModelCall):
            key = (ev.turn_index, ev.name or "")
            normalized: dict[str, str | int | float | None] = {}
            for k, v in ev.metadata.items():
                if isinstance(v, str | int | float) or v is None:
                    normalized[k] = v
                else:
                    normalized[k] = str(v)
            out[key] = normalized
    return out


def _order(causes: list[PossibleCause]) -> list[PossibleCause]:
    """Sort: computed (with contribution) first, then observed, then correlates.

    Within each tier, by absolute contribution_usd descending where defined.
    """
    def key(c: PossibleCause) -> tuple[int, float]:
        tier = {"computed": 0, "observed": 1, "correlates": 2}[c.confidence]
        contrib = -(c.contribution_usd or 0.0)
        return (tier, contrib)

    return sorted(causes, key=key)
