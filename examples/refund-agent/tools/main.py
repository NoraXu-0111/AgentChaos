"""Tool server for the refund-agent demo.

A standalone FastAPI app exposing the two tools the agent calls over real HTTP.
AgentChaos sits between the agent and this server as a forward-proxy, so faults
are injected at the network boundary (ADR-0003).
"""
from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request

app = FastAPI(title="AgentChaos refund-agent tools")


@app.get("/health")
def health() -> dict[str, bool]:
    return {"ok": True}


@app.post("/tools/get_order")
async def get_order(request: Request) -> dict[str, Any]:
    body = await request.json()
    order_id = str(body.get("order_id", "unknown"))
    return {
        "order_id": order_id,
        "status": "shipped",
        "customer_email": f"customer+{order_id}@example.com",
        "items": [{"sku": "WIDGET-1", "qty": 1}],
    }


@app.post("/tools/create_return_label")
async def create_return_label(request: Request) -> dict[str, Any]:
    body = await request.json()
    order_id = str(body.get("order_id", "unknown"))
    return {
        "order_id": order_id,
        "label_url": f"https://labels.example.com/{order_id}.pdf",
        "carrier": "UPS",
    }
