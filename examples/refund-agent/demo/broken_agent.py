"""Demo-only BROKEN variant of the refund agent (no graceful fallback).

Identical to ``server.main`` EXCEPT it does NOT catch a tool 5xx: when
``get_order`` returns a 503 (as injected by chaos) it lets the error propagate,
so FastAPI returns HTTP 500. AgentChaos observes the agent failing under an
injected fault and the run does NOT pass — exactly the regression a chaos gate
is meant to block before it reaches production.

This file lives under demo/ and is never imported by product code. It exists so
the CI-gate scenario can show a genuinely failing run alongside the passing one.
"""
from __future__ import annotations

import os
import re
from typing import Any

import httpx
from fastapi import FastAPI, Request

app = FastAPI(title="AgentChaos refund-agent demo (BROKEN fallback)")

_SESSIONS: dict[str, dict[str, Any]] = {}
_INPUT_TOKEN_COST = 0.00000015
_OUTPUT_TOKEN_COST = 0.00000060
_ORDER_RE = re.compile(r"\b(\d{4,8})\b")


def _tools_base_url() -> str:
    return os.environ.get("TOOLS_BASE_URL", "http://127.0.0.1:8090").rstrip("/")


def _rag_chunks(request: Request) -> int:
    q = request.query_params.get("rag_chunks")
    if q is not None:
        try:
            return max(1, int(q))
        except ValueError:
            pass
    return max(1, int(os.environ.get("RAG_CHUNKS", "5")))


def _cost(input_tokens: int, output_tokens: int) -> float:
    return round(input_tokens * _INPUT_TOKEN_COST + output_tokens * _OUTPUT_TOKEN_COST, 6)


async def _call_tool(client: httpx.AsyncClient, tool: str, payload: dict[str, Any]) -> httpx.Response:
    resp = await client.post(f"{_tools_base_url()}/tools/{tool}", json=payload, timeout=10.0)
    # BROKEN: no graceful handling — a 5xx tool response explodes the request.
    resp.raise_for_status()
    return resp


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/chat")
async def chat(request: Request) -> dict[str, Any]:
    body = await request.json()
    session_id = body.get("session_id") or "anon"
    message = (body.get("message") or "").strip()
    rag_chunks = _rag_chunks(request)

    state = _SESSIONS.setdefault(session_id, {"turn": 0, "order_id": None})
    state["turn"] += 1

    rag_tokens = 80 * rag_chunks
    base_input = 200
    planner_input = base_input + rag_tokens
    events: list[dict[str, Any]] = [
        {
            "type": "model_call",
            "name": "planner",
            "model": "gpt-4o-mini",
            "input_tokens": planner_input,
            "output_tokens": 40,
            "cost_usd": _cost(planner_input, 40),
            "latency_ms": 180 + 8 * rag_chunks,
            "metadata": {"rag_chunks": rag_chunks, "prompt_version": "refund-v3"},
        }
    ]

    order_match = _ORDER_RE.search(message)
    if state.get("order_id") is None and order_match:
        state["order_id"] = order_match.group(1)

    if state["order_id"] is None:
        return _respond(session_id, "Sure, I can help. What is your order number?", events)

    order_id = state["order_id"]
    async with httpx.AsyncClient() as client:
        # No try/except: an injected 503 raises HTTPStatusError → FastAPI 500.
        order_resp = await _call_tool(client, "get_order", {"order_id": order_id})
        events.append({
            "type": "tool_call", "name": "get_order",
            "args": {"order_id": order_id}, "result_summary": "ok", "retries": 0,
        })
        label_resp = await _call_tool(client, "create_return_label", {"order_id": order_id})
        _ = label_resp
        events.append({
            "type": "tool_call", "name": "create_return_label",
            "args": {"order_id": order_id}, "result_summary": "ok", "retries": 0,
        })

    final_in = base_input + rag_tokens + 50
    events.append({
        "type": "model_call", "name": "final_response", "model": "gpt-4o-mini",
        "input_tokens": final_in, "output_tokens": 70, "cost_usd": _cost(final_in, 70),
        "latency_ms": 220 + 8 * rag_chunks,
        "metadata": {"rag_chunks": rag_chunks, "prompt_version": "refund-v3"},
    })
    text = f"Found order #{order_id}. Your return label is on its way."
    return _respond(session_id, text, events)


def _respond(session_id: str, text: str, events: list[dict[str, Any]]) -> dict[str, Any]:
    total_input = sum(e.get("input_tokens", 0) for e in events if e["type"] == "model_call")
    total_output = sum(e.get("output_tokens", 0) for e in events if e["type"] == "model_call")
    return {
        "session_id": session_id,
        "message": text,
        "agent": {"name": "refund-agent-broken", "version": "0.0.1", "model": "gpt-4o-mini"},
        "events": events,
        "usage": {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost_usd": _cost(total_input, total_output),
        },
        "errors": [],
    }


@app.post("/control/reset")
async def reset() -> dict[str, str]:
    _SESSIONS.clear()
    return {"status": "reset"}
