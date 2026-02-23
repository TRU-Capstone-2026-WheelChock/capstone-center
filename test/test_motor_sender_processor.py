import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from capstone_center.motor_sender_processor import MotorSenderProcessor
from capstone_center.state_store import CoalescedUpdateSignal, DerivedState, RuntimeState
import capstone_center.motor_sender_processor as target


@pytest.mark.asyncio
async def test_decide_next_motor_state_prefers_override_folding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        target.msg_handler,
        "MotorState",
        SimpleNamespace(DEPLOYING="DEPLOYING", FOLDING="FOLDING"),
    )

    proc = MotorSenderProcessor(
        state=RuntimeState(),
        state_lock=asyncio.Lock(),
        derived_state=DerivedState(),
        derived_state_lock=asyncio.Lock(),
        signal_motor_process=CoalescedUpdateSignal(),
        pub_opt=object(),
    )

    assert proc.decide_next_motor_state(is_human=True, isin_override_mode=True) == "FOLDING"
    assert proc.decide_next_motor_state(is_human=True, isin_override_mode=False) == "DEPLOYING"
    assert proc.decide_next_motor_state(is_human=False, isin_override_mode=False) == "FOLDING"


@pytest.mark.asyncio
async def test_run_sends_motor_message_on_signal(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_event = asyncio.Event()
    sent_messages: list[SimpleNamespace] = []

    class _FakePublisher:
        async def send(self, data):
            sent_messages.append(data)
            sent_event.set()

    @asynccontextmanager
    async def _fake_publisher_ctx(_pub_opt):
        yield _FakePublisher()

    monkeypatch.setattr(target.msg_handler, "get_async_publisher", _fake_publisher_ctx)
    monkeypatch.setattr(
        target.msg_handler,
        "MotorState",
        SimpleNamespace(DEPLOYING="DEPLOYING", FOLDING="FOLDING"),
    )
    monkeypatch.setattr(
        target.msg_handler,
        "MotorMessage",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )

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
        pub_opt=object(),
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
