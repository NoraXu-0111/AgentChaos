"""Pydantic models for AgentChaos scenarios."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator

from agentchaos.budget.schema import Budget


class AgentTarget(BaseModel):
    """How AgentChaos reaches the agent under test."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["http"] = "http"
    endpoint: HttpUrl
    timeout_s: float = Field(default=30.0, gt=0)
    headers: dict[str, str] = Field(default_factory=dict)


class UserTurn(BaseModel):
    """One turn the simulated user sends to the agent."""

    model_config = ConfigDict(extra="forbid")

    user: str = Field(..., min_length=1)


class Expectation(BaseModel):
    """Lightweight task assertions. Not answer-quality scoring."""

    model_config = ConfigDict(extra="forbid")

    must_call_tools: list[str] = Field(default_factory=list)
    must_not_call_tools: list[str] = Field(default_factory=list)
    final_response_contains: list[str] = Field(default_factory=list)
    final_response_not_contains: list[str] = Field(default_factory=list)


class Scenario(BaseModel):
    """A reproducible reliability test for one tool-using agent."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    description: str = ""
    agent: AgentTarget
    conversation: list[UserTurn] = Field(..., min_length=1)
    expect: Expectation = Field(default_factory=Expectation)
    budgets: Budget = Field(default_factory=Budget)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _id_no_whitespace(cls, v: str) -> str:
        if any(c.isspace() for c in v):
            raise ValueError("scenario id must not contain whitespace")
        return v
