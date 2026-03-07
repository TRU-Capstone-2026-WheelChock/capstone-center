from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import pytest
import msg_handler
import capstone_center.motor_sender_processor as target

from capstone_center.motor_sender_processor import MotorSenderProcessor
from capstone_center.state_store import CoalescedUpdateSignal, DerivedState, RuntimeState


class FakeMotorState:
    DEPLOYING: str = "DEPLOYING"
    FOLDING: str = "FOLDING"


@dataclass(slots=True)
class FakeMotorMessage:
    sender_id: str
    is_override_mode: bool
    ordered_mode: str


def build_fake_motor_message(
    *,
    sender_id: str,
    is_override_mode: bool,
    ordered_mode: str,
) -> FakeMotorMessage:
    return FakeMotorMessage(
        sender_id=sender_id,
        is_override_mode=is_override_mode,
        ordered_mode=ordered_mode,
    )


def patch_motor_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace msg_handler.MotorState with a lightweight typed test double."""
    monkeypatch.setattr(target.msg_handler, "MotorState", FakeMotorState)


def patch_motor_msg_handler(
    monkeypatch: pytest.MonkeyPatch,
    sent_messages: list[FakeMotorMessage],
    sent_event: asyncio.Event | None = None,
) -> None:
    """Replace motor sender msg_handler dependencies with in-memory test doubles."""

    class _FakePublisher:
        async def send(self, data: FakeMotorMessage) -> None:
            sent_messages.append(data)
            if sent_event is not None:
                sent_event.set()

    @asynccontextmanager
    async def _fake_publisher_ctx(_pub_opt: object) -> AsyncIterator[_FakePublisher]:
        yield _FakePublisher()

    monkeypatch.setattr(target.msg_handler, "get_async_publisher", _fake_publisher_ctx)
    patch_motor_state(monkeypatch)
    monkeypatch.setattr(target.msg_handler, "MotorMessage", build_fake_motor_message)


def make_test_pub_opt() -> msg_handler.ZmqPubOptions:
    """Build a typed publisher option object for tests."""
    return msg_handler.ZmqPubOptions(endpoint="inproc://motor-sender-test")


@pytest.mark.asyncio
async def test_decide_next_motor_state_prefers_override_folding(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prefers folding in override mode and otherwise follows presence state.

    Mocking: patches `msg_handler.MotorState` with a lightweight typed test double.
    """
    patch_motor_state(monkeypatch)

    proc = MotorSenderProcessor(
        state=RuntimeState(),
        state_lock=asyncio.Lock(),
        derived_state=DerivedState(),
        derived_state_lock=asyncio.Lock(),
        signal_motor_process=CoalescedUpdateSignal(),
        pub_opt=make_test_pub_opt(),
    )

    assert proc.decide_next_motor_state(is_human=True, isin_override_mode=True) == "FOLDING"
    assert proc.decide_next_motor_state(is_human=True, isin_override_mode=False) == "DEPLOYING"
    assert proc.decide_next_motor_state(is_human=False, isin_override_mode=False) == "FOLDING"


@pytest.mark.asyncio
async def test_run_sends_motor_message_on_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sends one motor command immediately when the signal pipeline publishes an event.

    Mocking:
    - `patch_motor_msg_handler` replaces publisher/state/message dependencies with in-memory typed stand-ins.
    """
    sent_event = asyncio.Event()
    sent_messages: list[FakeMotorMessage] = []
    patch_motor_msg_handler(monkeypatch, sent_messages, sent_event=sent_event)

    state = RuntimeState()
    state.set_override_mode(False)
    derived_state = DerivedState(latest_is_human=True)
    signal_motor = CoalescedUpdateSignal()

    proc = MotorSenderProcessor(
        state=state,
        state_lock=asyncio.Lock(),
        derived_state=derived_state,
        derived_state_lock=asyncio.Lock(),
        signal_motor_process=signal_motor,
        pub_opt=make_test_pub_opt(),
        sender_id="motor-center",
        loop_time=60.0,
    )

    task = asyncio.create_task(proc.run())
    signal_motor.publish()

    await asyncio.wait_for(sent_event.wait(), timeout=1.0)

    assert len(sent_messages) == 1
    msg = sent_messages[0]
    assert msg.sender_id == "motor-center"
    assert msg.is_override_mode is False
    assert msg.ordered_mode == "DEPLOYING"

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_motor_sender_periodic_retry_sends_without_event(monkeypatch: pytest.MonkeyPatch) -> None:
    """Publishes periodic motor retries even when no signal event is received.

    Mocking:
    - `patch_motor_msg_handler` replaces `msg_handler` publisher/state/message dependencies with in-memory typed stand-ins.
    """
    sent_messages: list[FakeMotorMessage] = []
    patch_motor_msg_handler(monkeypatch, sent_messages)

    state = RuntimeState()
    state.set_override_mode(False)
    derived_state = DerivedState(latest_is_human=False)
    signal_motor = CoalescedUpdateSignal()

    proc = MotorSenderProcessor(
        state=state,
        state_lock=asyncio.Lock(),
        derived_state=derived_state,
        derived_state_lock=asyncio.Lock(),
        signal_motor_process=signal_motor,
        pub_opt=make_test_pub_opt(),
        sender_id="motor-center",
        loop_time=0.05,
    )

    task = asyncio.create_task(proc.run())
    try:
        deadline = asyncio.get_running_loop().time() + 0.8
        while len(sent_messages) < 2 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.02)

        assert len(sent_messages) >= 2
        assert all(msg.sender_id == "motor-center" for msg in sent_messages)
        assert all(msg.ordered_mode == "FOLDING" for msg in sent_messages)
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
