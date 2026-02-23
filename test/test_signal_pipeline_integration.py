import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime

import pytest

import capstone_center.msg_recv_processor as recv_target
from capstone_center.msg_recv_processor import MessageRecvProcessor
from capstone_center.sensor_information_processor import SensorInformationProcessor
from capstone_center.state_store import CoalescedUpdateSignal, DerivedState, RuntimeState


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


def _subscriber_factory(raw_items):
    @asynccontextmanager
    async def _ctx(_sub_opt):
        yield _AsyncIter(raw_items)

    return _ctx


@pytest.mark.asyncio
async def test_recv_to_sensor_processor_fans_out_display_and_motor_signals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    @dataclass
    class _FakeSensorPayload:
        isThereHuman: bool
        human_exist_possibility: float

    class _FakeSensorMessage:
        @staticmethod
        def model_validate(raw):
            return raw

    class _Msg:
        def __init__(self):
            self.data_type = "sensor"
            self.sender_id = "sensor-1"
            self.sender_name = "sensor"
            self.timestamp = datetime.now()
            self.payload = _FakeSensorPayload(isThereHuman=True, human_exist_possibility=0.9)

        def get_status(self):
            return 200, "OK"

    monkeypatch.setattr(recv_target.msg_handler, "SensorPayload", _FakeSensorPayload)
    monkeypatch.setattr(recv_target.msg_handler, "SensorMessage", _FakeSensorMessage)
    monkeypatch.setattr(
        recv_target.msg_handler,
        "get_async_subscriber",
        _subscriber_factory([_Msg()]),
    )

    state = RuntimeState()
    derived_state = DerivedState()
    state_lock = asyncio.Lock()
    derived_state_lock = asyncio.Lock()

    signal_sensor = CoalescedUpdateSignal(name="sensor")
    signal_display = CoalescedUpdateSignal(name="display")
    signal_motor = CoalescedUpdateSignal(name="motor")

    recv = MessageRecvProcessor(
        state=state,
        state_lock=state_lock,
        signal_sensor_process=signal_sensor,
        sub_opt=object(),
    )
    sensor_proc = SensorInformationProcessor(
        state=state,
        state_lock=state_lock,
        derived_state=derived_state,
        derived_state_lock=derived_state_lock,
        signal_sensor_process=signal_sensor,
        signal_display_process=signal_display,
        signal_motor_process=signal_motor,
    )

    sensor_task = asyncio.create_task(sensor_proc.run())
    display_waiter = asyncio.create_task(signal_display.wait_next())
    motor_waiter = asyncio.create_task(signal_motor.wait_next())

    await recv.run()

    await asyncio.wait_for(display_waiter, timeout=1.0)
    await asyncio.wait_for(motor_waiter, timeout=1.0)

    assert derived_state.revision == 1
    assert derived_state.latest_is_human is True
    assert derived_state.last_updated_at is not None

    sensor_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await sensor_task
