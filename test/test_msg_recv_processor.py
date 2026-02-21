import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import BaseModel

import capstone_center.msg_recv_processor as target
from capstone_center.msg_recv_processor import MessageRecvProcessor
from capstone_center.state_store import RuntimeState


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
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(), sub_opt=object())
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
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(), sub_opt=object())
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
async def test_run_ignores_unknown_data_type(monkeypatch: pytest.MonkeyPatch):
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(), sub_opt=object())
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
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(), sub_opt=object())
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
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(), sub_opt=object())
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
async def test_run_uses_sub_opt_for_subscriber(monkeypatch: pytest.MonkeyPatch):
    sub_opt = object()
    captured = []
    p = MessageRecvProcessor(RuntimeState(), asyncio.Lock(), sub_opt=sub_opt)
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
