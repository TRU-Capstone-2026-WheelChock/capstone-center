import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

import capstone_center.motor_sender_processor as target
from capstone_center.motor_sender_processor import MotorSenderProcessor
from capstone_center.state_store import CoalescedUpdateSignal, DerivedState, RuntimeState


@pytest.mark.asyncio
async def test_motor_sender_periodic_retry_sends_without_event(monkeypatch: pytest.MonkeyPatch) -> None:
    sent_messages: list[SimpleNamespace] = []

    class _FakePublisher:
        async def send(self, data):
            sent_messages.append(data)

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
    derived_state = DerivedState(latest_is_human=False)
    signal_motor = CoalescedUpdateSignal()

    proc = MotorSenderProcessor(
        state=state,
        state_lock=asyncio.Lock(),
        derived_state=derived_state,
        derived_state_lock=asyncio.Lock(),
        signal_motor_process=signal_motor,
        pub_opt=object(),
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
