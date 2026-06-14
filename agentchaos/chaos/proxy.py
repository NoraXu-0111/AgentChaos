"""In-process HTTP forward-proxy that injects chaos on the agent->tool path.

The agent is pointed at this proxy via ``TOOLS_BASE_URL``. For each inbound
request the proxy derives the tool name from the path, applies the seeded
``ChaosPolicy``, injects faults (status_code short-circuits the upstream;
latency sleeps then forwards), forwards survivors to the real upstream tool, and
records ``chaos_injected`` + ``tool_response`` events into the shared trace.

The proxy never raises on upstream failures: an unreachable or erroring upstream
becomes a recorded 502 ``tool_response``.
"""
from __future__ import annotations

import asyncio
import json as _json
import random
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, ConfigDict, Field

from agentchaos.chaos.injectors import decide_injection
from agentchaos.chaos.policy import ChaosPolicy
from agentchaos.seq import SeqCounter
from agentchaos.trace.recorder import TraceRecorder
from agentchaos.trace.schema import ChaosInjected, ToolResponse

# Headers worth keeping in the trace; everything else is dropped.
_HEADER_ALLOWLIST = ("content-type", "x-chaos", "x-request-id")


class ProxyResponse(BaseModel):
    """What the proxy returns to the agent for one tool request."""

    model_config = ConfigDict(extra="forbid")

    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: bytes

    def header_items(self) -> list[tuple[str, str]]:
        return list(self.headers.items())


def tool_name_from_path(path: str) -> str:
    """Last non-empty path segment, stripped of query string and trailing slash."""
    no_query = urlsplit(path).path
    segments = [seg for seg in no_query.split("/") if seg]
    return segments[-1] if segments else ""


def _headers_subset(headers: dict[str, str]) -> dict[str, str]:
    lowered = {k.lower(): v for k, v in headers.items()}
    return {k: lowered[k] for k in _HEADER_ALLOWLIST if k in lowered}


def _parse_json_body(raw: bytes) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        parsed = _json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


class ChaosProxy:
    """Apply a seeded chaos policy and forward survivors upstream."""

    def __init__(
        self,
        *,
        upstream_base_url: str,
        policy: ChaosPolicy,
        seed: int,
        recorder: TraceRecorder,
        seq: SeqCounter,
        run_id: str,
        session_id: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._upstream = upstream_base_url.rstrip("/")
        self._policy = policy
        self._recorder = recorder
        self._seq = seq
        self._run_id = run_id
        self._session_id = session_id
        self._rng = random.Random(seed)
        self._injected_count = 0
        if client is not None:
            self._client = client
            self._owns_client = False
        else:
            self._client = httpx.AsyncClient(timeout=30.0)
            self._owns_client = True

    @property
    def injected_count(self) -> int:
        return self._injected_count

    async def handle(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
    ) -> ProxyResponse:
        """Apply chaos then forward; record tool_response. Never raises."""
        tool_name = tool_name_from_path(path)
        # Best-effort correlation with tool_call events is by tool_name+args_hash;
        # exact call_index linkage is deferred (Phase 11 record/replay).
        args_hash = self._maybe_args_hash(body)
        policy = self._policy.policy_for(tool_name)

        if policy is None:
            return await self._forward(method, path, headers, body, tool_name, args_hash, False)

        decision = decide_injection(policy, self._rng)

        if decision.inject and decision.injection_type == "status_code":
            self._injected_count += 1
            status = decision.status_code or 503
            self._record_chaos(tool_name, decision.policy_desc, "status_code", status, args_hash)
            injected_body = _json.dumps(
                {"error": "chaos_injected", "status": status, "tool": tool_name}
            ).encode("utf-8")
            self._record_tool_response(
                tool_name, status, injected_body, {"content-type": "application/json"},
                chaos=True, args_hash=args_hash,
            )
            return ProxyResponse(
                status=status,
                headers={"content-type": "application/json", "x-chaos": "injected"},
                body=injected_body,
            )

        if decision.inject and decision.injection_type == "latency":
            self._injected_count += 1
            self._record_chaos(
                tool_name, decision.policy_desc, "latency", decision.latency_ms, args_hash
            )
            await asyncio.sleep(decision.latency_ms / 1000.0)
            return await self._forward(method, path, headers, body, tool_name, args_hash, True)

        return await self._forward(method, path, headers, body, tool_name, args_hash, False)

    async def _forward(
        self,
        method: str,
        path: str,
        headers: dict[str, str],
        body: bytes,
        tool_name: str,
        args_hash: str | None,
        chaos: bool,
    ) -> ProxyResponse:
        url = f"{self._upstream}{urlsplit(path).path}"
        fwd_headers = {k: v for k, v in headers.items() if k.lower() != "host"}
        try:
            resp = await self._client.request(method, url, content=body, headers=fwd_headers)
        except httpx.HTTPError as exc:
            err_body = _json.dumps(
                {"error": "upstream_unreachable", "detail": repr(exc), "tool": tool_name}
            ).encode("utf-8")
            self._record_tool_response(
                tool_name, 502, err_body, {"content-type": "application/json"},
                chaos=chaos, args_hash=args_hash,
            )
            return ProxyResponse(
                status=502,
                headers={"content-type": "application/json"},
                body=err_body,
            )

        resp_headers = dict(resp.headers.items())
        self._record_tool_response(
            tool_name, resp.status_code, resp.content, resp_headers,
            chaos=chaos, args_hash=args_hash,
        )
        return ProxyResponse(
            status=resp.status_code,
            headers=resp_headers,
            body=resp.content,
        )

    def _maybe_args_hash(self, body: bytes) -> str | None:
        parsed = _parse_json_body(body)
        if parsed is None:
            return None
        from agentchaos.runner.session import args_hash as _hash

        return _hash(parsed)

    def _record_chaos(
        self, tool_name: str, policy_desc: str, injection_type: str, value: int,
        args_hash: str | None,
    ) -> None:
        self._recorder.write(
            ChaosInjected(
                run_id=self._run_id,
                seq=self._seq.take(),
                timestamp=datetime.now(UTC),
                session_id=self._session_id,
                target=tool_name,
                policy=policy_desc,
                injection_type=injection_type,  # type: ignore[arg-type]
                value=value,
                tool_name=tool_name,
                args_hash=args_hash,
            )
        )

    def _record_tool_response(
        self, tool_name: str, status: int, body: bytes, headers: dict[str, str],
        *, chaos: bool, args_hash: str | None,
    ) -> None:
        self._recorder.write(
            ToolResponse(
                run_id=self._run_id,
                seq=self._seq.take(),
                timestamp=datetime.now(UTC),
                session_id=self._session_id,
                tool_name=tool_name,
                status=status,
                size_bytes=len(body),
                headers_subset=_headers_subset(headers),
                body=_parse_json_body(body),
                chaos_injected=chaos,
                args_hash=args_hash,
            )
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
