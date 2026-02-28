import asyncio
from datetime import datetime, timedelta

import pytest

from capstone_center.heartbeat_process import HeartbeatConfig, HeartbeatProcessor
from capstone_center.state_store import ComponentHeartbeat, RuntimeState


@pytest.mark.asyncio
async def test_heartbeat_process_marks_dead_after_timeout() -> None:
    now = datetime.now()
    state = RuntimeState()
    state.heartbeats["c-1"] = ComponentHeartbeat(last_seen=now - timedelta(seconds=6))

    proc = HeartbeatProcessor(
        state=state,
        state_lock=asyncio.Lock(),
        hb_config=HeartbeatConfig(loop_time=1.0, timeout_threshold=5.0, remove_threshold=60.0),
    )
    await proc.heartbeat_process(now=now, timeout_threshold=5.0, remove_threshold=60.0)

    assert "c-1" in state.dead_components_set
    assert "c-1" in state.heartbeats


@pytest.mark.asyncio
async def test_heartbeat_process_removes_after_remove_threshold() -> None:
    now = datetime.now()
    state = RuntimeState()
    state.heartbeats["c-2"] = ComponentHeartbeat(last_seen=now - timedelta(seconds=61))

    proc = HeartbeatProcessor(
        state=state,
        state_lock=asyncio.Lock(),
        hb_config=HeartbeatConfig(loop_time=1.0, timeout_threshold=5.0, remove_threshold=60.0),
    )
    await proc.heartbeat_process(now=now, timeout_threshold=5.0, remove_threshold=60.0)

    assert "c-2" in state.dead_components_set
    assert "c-2" not in state.heartbeats


@pytest.mark.asyncio
async def test_heartbeat_runner_rejects_non_positive_params() -> None:
    proc = HeartbeatProcessor(
        state=RuntimeState(),
        state_lock=asyncio.Lock(),
        hb_config=HeartbeatConfig(loop_time=1.0, timeout_threshold=5.0, remove_threshold=60.0),
    )

    with pytest.raises(ValueError):
        await proc.heartbeat_runner(loop_time=0, timeout_threshold=5.0, remove_threshold=60.0)


@pytest.mark.asyncio
async def test_heartbeat_runner_propagates_cancel(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = HeartbeatProcessor(
        state=RuntimeState(),
        state_lock=asyncio.Lock(),
        hb_config=HeartbeatConfig(loop_time=1.0, timeout_threshold=5.0, remove_threshold=60.0),
    )

    async def cancel_sleep(_seconds: float) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr("capstone_center.heartbeat_process.asyncio.sleep", cancel_sleep)

    with pytest.raises(asyncio.CancelledError):
        await proc.heartbeat_runner(loop_time=1.0, timeout_threshold=5.0, remove_threshold=60.0)


@pytest.mark.asyncio
async def test_heartbeat_process_keeps_component_alive_when_recent_signal_arrives() -> None:
    now = datetime.now()
    state = RuntimeState()
    state.heartbeats["sensor-1"] = ComponentHeartbeat(last_seen=now - timedelta(seconds=20))
    state.dead_components_set.add("sensor-1")

    # Simulate a fresh signal update before watchdog runs again.
    state.mark_heartbeat("sensor-1", now - timedelta(milliseconds=100))

    proc = HeartbeatProcessor(
        state=state,
        state_lock=asyncio.Lock(),
        hb_config=HeartbeatConfig(loop_time=1.0, timeout_threshold=5.0, remove_threshold=60.0),
    )
    await proc.heartbeat_process(now=now, timeout_threshold=5.0, remove_threshold=60.0)

    assert "sensor-1" not in state.dead_components_set
