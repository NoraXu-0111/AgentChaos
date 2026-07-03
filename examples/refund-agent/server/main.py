"""Toy customer-support refund agent.

A FastAPI server that pretends to be a tool-using refund agent. It speaks the
AgentChaos full-fidelity HTTP contract (``message`` + ``events[]`` + ``usage``)
so AgentChaos can record realistic cost/tool/retry behavior without any real
LLM call.

The ``rag_chunks`` knob (``RAG_CHUNKS`` env var or ``?rag_chunks=N`` query
param) controls how many fake retrieval chunks the planner consumes — higher
values inflate input tokens and cost. This is the demo's cost-regression knob.
"""
from __future__ import annotations

import os
import re
from typing import Any

from fastapi import FastAPI, Request

app = FastAPI(title="AgentChaos refund-agent demo")

# In-memory session state. Real agents would use a store.
_SESSIONS: dict[str, dict[str, Any]] = {}

# Crude cost model: token count x per-token rate. Realistic enough for demo.
_INPUT_TOKEN_COST = 0.00000015  # ~ gpt-4o-mini input
_OUTPUT_TOKEN_COST = 0.00000060

_ORDER_RE = re.compile(r"\b(\d{4,8})\b")


def _int_knob(request: Request, name: str, env: str, default: int, *, floor: int) -> int:
    """Read an int knob from query param, then env var; clamp to ``floor``."""
    q = request.query_params.get(name)
    if q is not None:
        try:
            return max(floor, int(q))
        except ValueError:
            pass
    return max(floor, int(os.environ.get(env, str(default))))


def _rag_chunks(request: Request) -> int:
    """Read rag_chunks from query param, then env var, default 5."""
    return _int_knob(request, "rag_chunks", "RAG_CHUNKS", 5, floor=1)


def _retry_storm(request: Request) -> int:
    """Read retry_storm from query param, then env var, default 0 (disabled)."""
    return _int_knob(request, "retry_storm", "RETRY_STORM", 0, floor=0)


def _cost(input_tokens: int, output_tokens: int) -> float:
    return round(
        input_tokens * _INPUT_TOKEN_COST + output_tokens * _OUTPUT_TOKEN_COST, 6
    )


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/chat")
async def chat(request: Request) -> dict[str, Any]:
    body = await request.json()
    session_id = body.get("session_id") or "anon"
    message = (body.get("message") or "").strip()
    rag_chunks = _rag_chunks(request)
    retry_storm = _retry_storm(request)

    state = _SESSIONS.setdefault(session_id, {"turn": 0, "order_id": None})
    state["turn"] += 1

    # The "planner" consumes the user message plus N fake retrieval chunks.
    # Each chunk = ~80 tokens.
    rag_tokens = 80 * rag_chunks
    base_input = 200  # system prompt + history
    planner_input = base_input + rag_tokens
    planner_output = 40

    events: list[dict[str, Any]] = [
        {
            "type": "model_call",
            "name": "planner",
            "model": "gpt-4o-mini",
            "input_tokens": planner_input,
            "output_tokens": planner_output,
            "cost_usd": _cost(planner_input, planner_output),
            "latency_ms": 180 + 8 * rag_chunks,
            "metadata": {"rag_chunks": rag_chunks, "prompt_version": "refund-v3"},
        }
    ]

    text = ""
    order_match = _ORDER_RE.search(message)
    if state.get("order_id") is None and order_match:
        state["order_id"] = order_match.group(1)

    if state["order_id"] is None:
        # First turn — ask for the order number.
        text = "Sure, I can help. What is your order number?"
    else:
        # Second turn — look up the order and create a return label.
        order_id = state["order_id"]
        # Retry-storm knob: emit N identical get_order calls before the normal one.
        for _ in range(retry_storm):
            events.append(
                {
                    "type": "tool_call",
                    "name": "get_order",
                    "args": {"order_id": order_id},
                    "latency_ms": 60,
                    "result_summary": "ok",
                    "retries": 0,
                }
            )
        events.append(
            {
                "type": "tool_call",
                "name": "get_order",
                "args": {"order_id": order_id},
                "latency_ms": 60,
                "result_summary": "ok",
                "retries": 0,
            }
        )
        events.append(
            {
                "type": "tool_call",
                "name": "create_return_label",
                "args": {"order_id": order_id},
                "latency_ms": 90,
                "result_summary": "ok",
                "retries": 0,
            }
        )
        # A second planner call to formulate the final response.
        final_in = base_input + rag_tokens + 50
        final_out = 70
        events.append(
            {
                "type": "model_call",
                "name": "final_response",
                "model": "gpt-4o-mini",
                "input_tokens": final_in,
                "output_tokens": final_out,
                "cost_usd": _cost(final_in, final_out),
                "latency_ms": 220 + 8 * rag_chunks,
                "metadata": {"rag_chunks": rag_chunks, "prompt_version": "refund-v3"},
            }
        )
        text = (
            f"Found order #{order_id}. Your return label is on its way; "
            "check your email for the refund details."
        )

    # Aggregate usage across all model calls in this turn.
    total_input = sum(e.get("input_tokens", 0) for e in events if e["type"] == "model_call")
    total_output = sum(e.get("output_tokens", 0) for e in events if e["type"] == "model_call")
    usage = {
        "input_tokens": total_input,
        "output_tokens": total_output,
        "cost_usd": _cost(total_input, total_output),
    }

    return {
        "session_id": session_id,
        "message": text,
        "agent": {"name": "refund-agent", "version": "0.1.0", "model": "gpt-4o-mini"},
        "events": events,
        "usage": usage,
        "errors": [],
    }


@app.post("/control/reset")
async def reset() -> dict[str, str]:
    _SESSIONS.clear()
    return {"status": "reset"}
