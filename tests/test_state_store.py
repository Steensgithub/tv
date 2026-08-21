"""
tests/test_state_store.py – unit tests for deduplication state.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from storage import StateStore


@pytest.fixture
def store(tmp_path):
    return StateStore(str(tmp_path / "state.json"))


@pytest.mark.asyncio
async def test_first_signal_not_duplicate(store):
    ts = datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
    assert not await store.is_duplicate("AAPL", "1d", ts)


@pytest.mark.asyncio
async def test_duplicate_after_record(store):
    ts = datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
    await store.record("AAPL", "1d", ts)
    assert await store.is_duplicate("AAPL", "1d", ts)


@pytest.mark.asyncio
async def test_earlier_bar_is_duplicate(store):
    ts = datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
    ts_earlier = datetime(2024, 1, 14, 20, 0, 0, tzinfo=timezone.utc)
    await store.record("AAPL", "1d", ts)
    assert await store.is_duplicate("AAPL", "1d", ts_earlier)


@pytest.mark.asyncio
async def test_later_bar_is_not_duplicate(store):
    ts = datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
    ts_later = datetime(2024, 1, 16, 20, 0, 0, tzinfo=timezone.utc)
    await store.record("AAPL", "1d", ts)
    assert not await store.is_duplicate("AAPL", "1d", ts_later)


@pytest.mark.asyncio
async def test_different_symbol_independent(store):
    ts = datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
    await store.record("AAPL", "1d", ts)
    assert not await store.is_duplicate("MSFT", "1d", ts)


@pytest.mark.asyncio
async def test_different_timeframe_independent(store):
    ts = datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
    await store.record("AAPL", "1d", ts)
    assert not await store.is_duplicate("AAPL", "1h", ts)


@pytest.mark.asyncio
async def test_persistence(tmp_path):
    path = str(tmp_path / "state.json")
    ts = datetime(2024, 1, 15, 20, 0, 0, tzinfo=timezone.utc)
    store1 = StateStore(path)
    await store1.record("AAPL", "1d", ts)
    # Load fresh instance from same file
    store2 = StateStore(path)
    assert await store2.is_duplicate("AAPL", "1d", ts)
