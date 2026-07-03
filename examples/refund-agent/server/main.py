"""Toy customer-support refund agent.

A FastAPI server that pretends to be a tool-using refund agent. It speaks the
AgentChaos full-fidelity HTTP contract (``message`` + ``events[]`` + ``usage``)
so AgentChaos can record realistic cost/tool/retry behavior without any real
LLM call.

Tools are REAL outbound HTTP calls to ``TOOLS_BASE_URL`` (default
``http://127.0.0.1:8090``). When AgentChaos runs a chaos scenario it points this
agent at its forward-proxy via ``TOOLS_BASE_URL``; injected faults therefore
arrive as genuine 5xx responses on the tool calls.

On a tool 5xx the agent takes an OBSERVABLE fallback path: it stops, skips the
remaining tools, and returns a graceful "a human agent will follow up" message.

The ``rag_chunks`` knob (``RAG_CHUNKS`` env var or ``?rag_chunks=N`` query
param) controls how many fake retrieval chunks the planner consumes — higher
values inflate input tokens and cost. This is the demo's cost-regression knob.

The ``retry_storm`` knob (``RETRY_STORM`` env var or ``?retry_storm=N``) emits
N identical ``get_order`` tool calls before the real one — the demo trigger for
the loop/retry-storm detectors.
"""
from __future__ import annotations

import os
import re
from typing import Any

import httpx
from fastapi import FastAPI, Request

app = FastAPI(title="AgentChaos refund-agent demo")

# In-memory session state. Real agents would use a store.
_SESSIONS: dict[str, dict[str, Any]] = {}

# Crude cost model: token count x per-token rate. Realistic enough for demo.
_INPUT_TOKEN_COST = 0.00000015  # ~ gpt-4o-mini input
_OUTPUT_TOKEN_COST = 0.00000060

_ORDER_RE = re.compile(r"\b(\d{4,8})\b")

_FALLBACK_TEXT = (
    "I'm having trouble looking up your order right now; "
    "a human agent will follow up."
)


def _tools_base_url() -> str:
    return os.environ.get("TOOLS_BASE_URL", "http://127.0.0.1:8090").rstrip("/")


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


async def _call_tool(client: httpx.AsyncClient, tool: str, payload: dict[str, Any]) -> httpx.Response:
    return await client.post(f"{_tools_base_url()}/tools/{tool}", json=payload, timeout=10.0)


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
        text = "Sure, I can help. What is your order number?"
        return _respond(session_id, text, events)

    order_id = state["order_id"]

    # Retry-storm knob: emit N identical get_order calls before the real one.
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

    async with httpx.AsyncClient() as client:
        # Tool 1: get_order (a real outbound HTTP call).
        try:
            order_resp = await _call_tool(client, "get_order", {"order_id": order_id})
        except httpx.HTTPError:
            order_resp = None  # type: ignore[assignment]

        if order_resp is None or order_resp.status_code >= 500:
            events.append({
                "type": "tool_call",
                "name": "get_order",
                "args": {"order_id": order_id},
                "result_summary": "error",
                "retries": 0,
            })
            # Observable fallback: skip remaining tools, return a graceful message.
            return _respond(session_id, _FALLBACK_TEXT, events)

        events.append({
            "type": "tool_call",
            "name": "get_order",
            "args": {"order_id": order_id},
            "result_summary": "ok",
            "retries": 0,
        })

        # Tool 2: create_return_label.
        try:
            label_resp = await _call_tool(
                client, "create_return_label", {"order_id": order_id}
            )
        except httpx.HTTPError:
            label_resp = None  # type: ignore[assignment]

        if label_resp is None or label_resp.status_code >= 500:
            events.append({
                "type": "tool_call",
                "name": "create_return_label",
                "args": {"order_id": order_id},
                "result_summary": "error",
                "retries": 0,
            })
            return _respond(session_id, _FALLBACK_TEXT, events)

        events.append({
            "type": "tool_call",
            "name": "create_return_label",
            "args": {"order_id": order_id},
            "result_summary": "ok",
            "retries": 0,
        })

    final_in = base_input + rag_tokens + 50
    final_out = 70
    events.append({
        "type": "model_call",
        "name": "final_response",
        "model": "gpt-4o-mini",
        "input_tokens": final_in,
        "output_tokens": final_out,
        "cost_usd": _cost(final_in, final_out),
        "latency_ms": 220 + 8 * rag_chunks,
        "metadata": {"rag_chunks": rag_chunks, "prompt_version": "refund-v3"},
    })
    text = (
        f"Found order #{order_id}. Your return label is on its way; "
        "check your email for the refund details."
    )
    return _respond(session_id, text, events)


def _respond(session_id: str, text: str, events: list[dict[str, Any]]) -> dict[str, Any]:
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
        "agent": {"name": "refund-agent", "version": "0.2.0", "model": "gpt-4o-mini"},
        "events": events,
        "usage": usage,
        "errors": [],
    }


@app.post("/control/reset")
async def reset() -> dict[str, str]:
    _SESSIONS.clear()
    return {"status": "reset"}
