import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

import capstone_center.msg_recv_processor as target
from capstone_center.msg_recv_processor import MessageRecvProcessor
from capstone_center.state_store import RuntimeState, CoalescedUpdateSignal


class _AsyncIter:
    def __init__(self, items):
        self._iter = iter(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration:
            raise StopAsyncIteration


def _subscriber_factory(raw_items, captured_sub_opts=None):
    @asynccontextmanager
    async def _ctx(sub_opt):
        if captured_sub_opts is not None:
            captured_sub_opts.append(sub_opt)
        yield _AsyncIter(raw_items)

    return _ctx


def _patch_model_validate(monkeypatch: pytest.MonkeyPatch, validate_fn):
    class _FakeSensorMessage:
        @staticmethod
        def model_validate(raw):
            return validate_fn(raw)

    monkeypatch.setattr(target.msg_handler, "SensorMessage", _FakeSensorMessage)


@pytest.mark.asyncio
async def test_run_dispatches_heartbeat_to_other_handler(monkeypatch: pytest.MonkeyPatch):
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(),CoalescedUpdateSignal(), sub_opt=object())
    p._other_msg_handler = AsyncMock()
    p._sensor_msg_handler = AsyncMock()

    monkeypatch.setattr(
        target.msg_handler,
        "get_async_subscriber",
        _subscriber_factory([{"raw": 1}]),
    )
    _patch_model_validate(
        monkeypatch,
        lambda _raw: SimpleNamespace(data_type="heartbeat", payload=object()),
    )

    await p.run()

    p._other_msg_handler.assert_awaited_once()
    p._sensor_msg_handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_dispatches_sensor_to_sensor_handler(monkeypatch: pytest.MonkeyPatch):
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(),CoalescedUpdateSignal(), sub_opt=object())
    p._other_msg_handler = AsyncMock()
    p._sensor_msg_handler = AsyncMock()

    monkeypatch.setattr(
        target.msg_handler,
        "get_async_subscriber",
        _subscriber_factory([{"raw": 1}]),
    )
    _patch_model_validate(
        monkeypatch,
        lambda _raw: SimpleNamespace(data_type="sensor", payload=object()),
    )

    await p.run()

    p._sensor_msg_handler.assert_awaited_once()
    p._other_msg_handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_dispatches_override_button_to_override_handler(monkeypatch: pytest.MonkeyPatch):
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(), CoalescedUpdateSignal(), sub_opt=object())
    p._other_msg_handler = AsyncMock()
    p._sensor_msg_handler = AsyncMock()
    p._override_button = AsyncMock()

    monkeypatch.setattr(
        target.msg_handler,
        "get_async_subscriber",
        _subscriber_factory([{"raw": 1}]),
    )
    monkeypatch.setattr(
        target.msg_handler,
        "GenericMessageDatatype",
        SimpleNamespace(OVERRIDE_BUTTON="override_button"),
    )
    _patch_model_validate(
        monkeypatch,
        lambda _raw: SimpleNamespace(data_type="override_button", payload=object()),
    )

    await p.run()

    p._override_button.assert_awaited_once()
    p._other_msg_handler.assert_not_awaited()
    p._sensor_msg_handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_ignores_unknown_data_type(monkeypatch: pytest.MonkeyPatch):
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(),CoalescedUpdateSignal(), sub_opt=object())
    p._other_msg_handler = AsyncMock()
    p._sensor_msg_handler = AsyncMock()

    monkeypatch.setattr(
        target.msg_handler,
        "get_async_subscriber",
        _subscriber_factory([{"raw": 1}]),
    )
    _patch_model_validate(
        monkeypatch,
        lambda _raw: SimpleNamespace(data_type="unknown", payload=object()),
    )

    await p.run()

    p._other_msg_handler.assert_not_awaited()
    p._sensor_msg_handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_continues_after_validation_error(monkeypatch: pytest.MonkeyPatch):
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(),CoalescedUpdateSignal(), sub_opt=object())
    p._other_msg_handler = AsyncMock()
    p._sensor_msg_handler = AsyncMock()

    monkeypatch.setattr(
        target.msg_handler,
        "get_async_subscriber",
        _subscriber_factory(["bad", "ok"]),
    )

    class _Tmp(BaseModel):
        n: int

    def _validate(raw):
        if raw == "bad":
            _Tmp.model_validate({"n": "x"})  # raises ValidationError
        return SimpleNamespace(data_type="heartbeat", payload=object())

    _patch_model_validate(monkeypatch, _validate)

    await p.run()

    p._other_msg_handler.assert_awaited_once()
    p._sensor_msg_handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_continues_after_assertion_error(monkeypatch: pytest.MonkeyPatch):
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(),CoalescedUpdateSignal(), sub_opt=object())
    p._other_msg_handler = AsyncMock()
    p._sensor_msg_handler = AsyncMock(side_effect=AssertionError("boom"))

    monkeypatch.setattr(
        target.msg_handler,
        "get_async_subscriber",
        _subscriber_factory(["sensor", "heartbeat"]),
    )

    def _validate(raw):
        if raw == "sensor":
            return SimpleNamespace(data_type="sensor", payload=object())
        return SimpleNamespace(data_type="heartbeat", payload=object())

    _patch_model_validate(monkeypatch, _validate)

    await p.run()

    p._sensor_msg_handler.assert_awaited_once()
    p._other_msg_handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_override_sets_override_mode_true_for_override_status() -> None:
    state = RuntimeState()
    p = MessageRecvProcessor(state, asyncio.Lock(), CoalescedUpdateSignal(), sub_opt=object())
    payload = target.msg_handler.schemas.HeartBeatPayload(status="override", status_code=200)

    await p._handle_override(SimpleNamespace(payload=payload))

    assert state.isin_override_mode is True


@pytest.mark.asyncio
async def test_handle_override_sets_override_mode_false_for_non_override_status() -> None:
    state = RuntimeState()
    state.set_override_mode(True)
    p = MessageRecvProcessor(state, asyncio.Lock(), CoalescedUpdateSignal(), sub_opt=object())
    payload = target.msg_handler.schemas.HeartBeatPayload(status="active", status_code=200)

    await p._handle_override(SimpleNamespace(payload=payload))

    assert state.isin_override_mode is False


@pytest.mark.asyncio
async def test_run_uses_sub_opt_for_subscriber(monkeypatch: pytest.MonkeyPatch):
    sub_opt = object()
    captured = []
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(),CoalescedUpdateSignal(), sub_opt=sub_opt)
    p._other_msg_handler = AsyncMock()
    p._sensor_msg_handler = AsyncMock()

    monkeypatch.setattr(
        target.msg_handler,
        "get_async_subscriber",
        _subscriber_factory([], captured_sub_opts=captured),
    )
    _patch_model_validate(
        monkeypatch,
        lambda _raw: SimpleNamespace(data_type="heartbeat", payload=object()),
    )

    await p.run()

    assert captured == [sub_opt]


@pytest.mark.asyncio
async def test_handle_heart_beat_uses_receiver_time_not_message_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixed_now = datetime(2026, 2, 28, 4, 40, 45)
    old_msg_time = fixed_now - timedelta(seconds=59)

    class _FakeDatetime:
        @classmethod
        def now(cls):
            return fixed_now

    monkeypatch.setattr(target, "datetime", _FakeDatetime)

    state = RuntimeState()
    p = MessageRecvProcessor(state, asyncio.Lock(), CoalescedUpdateSignal(), sub_opt=object())
    msg = SimpleNamespace(sender_id="sensor-1", sender_name="sensor", timestamp=old_msg_time)

    await p._handle_heart_beat(msg)

    assert state.heartbeats["sensor-1"].last_seen == fixed_now
    assert state.heartbeats["sensor-1"].last_seen != old_msg_time
