"""Transport interface and the result type returned per agent turn."""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class FidelityTier(StrEnum):
    """How much detail the agent emits in its response."""

    FULL = "full"
    AGGREGATE = "aggregate"
    MESSAGE_ONLY = "message_only"


class AgentTurnResult(BaseModel):
    """Outcome of one user→agent turn, normalised across fidelity tiers."""

    model_config = ConfigDict(extra="forbid")

    text: str
    events: list[dict[str, Any]] = Field(default_factory=list)
    usage: dict[str, Any] | None = None
    agent: dict[str, Any] | None = None
    fidelity: FidelityTier = FidelityTier.FULL
    latency_ms: int
    ttft_ms: int | None = None
    error: str | None = None
    status_code: int | None = None


class AgentTransport(ABC):
    """How AgentChaos talks to the agent under test."""

    @abstractmethod
    async def send(self, session_id: str, message: str) -> AgentTurnResult:
        """Send one user message; return the agent's full response (incl. tool calls)."""

    async def aclose(self) -> None:  # noqa: B027 — optional override, intentionally empty
        """Override if transport-level cleanup is needed."""
