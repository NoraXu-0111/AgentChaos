"""Tests for the shared SeqCounter."""
from __future__ import annotations

import asyncio

from agentchaos.seq import SeqCounter


def test_take_is_monotonic() -> None:
    c = SeqCounter()
    assert [c.take() for _ in range(5)] == [0, 1, 2, 3, 4]


def test_take_respects_start() -> None:
    c = SeqCounter(start=10)
    assert c.take() == 10
    assert c.take() == 11


def test_value_has_no_side_effect() -> None:
    c = SeqCounter(start=3)
    assert c.value == 3
    assert c.value == 3  # reading twice must not advance
    assert c.take() == 3
    assert c.value == 4


async def test_concurrent_takes_are_unique() -> None:
    c = SeqCounter()

    async def grab() -> int:
        return c.take()

    results = await asyncio.gather(*(grab() for _ in range(200)))
    assert len(set(results)) == 200
    assert sorted(results) == list(range(200))
