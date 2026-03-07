import asyncio
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from types import SimpleNamespace

import pytest

import capstone_center.display_sender_processor as display_target
import capstone_center.motor_sender_processor as motor_target
import capstone_center.msg_recv_processor as recv_target
from capstone_center.display_sender_processor import DisplaySenderProcessor
from capstone_center.motor_sender_processor import MotorSenderProcessor
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
    """Verifies that one sensor message propagates through derived-state fan-out signals.

    Mocking:
    - `msg_handler.SensorPayload` is replaced with a lightweight fake payload class.
    - `msg_handler.SensorMessage` is replaced with a trivial validator that returns the raw object.
    - `msg_handler.get_async_subscriber` is replaced with an in-memory async iterator.
    """
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


@pytest.mark.asyncio
async def test_override_event_reaches_display_and_motor_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verifies that override mode reaches both display and motor publishers.

    Mocking:
    - display and motor `msg_handler.get_async_publisher` functions are replaced with in-memory publishers.
    - `DisplayMessage`, `MotorState`, and `MotorMessage` are patched with lightweight stand-ins.
    - The override payload uses the real `msg_handler` heartbeat schema.
    """
    display_sent = asyncio.Event()
    motor_sent = asyncio.Event()
    display_messages: list[SimpleNamespace] = []
    motor_messages: list[SimpleNamespace] = []

    class _DisplayPublisher:
        async def send(self, data):
            display_messages.append(data)
            display_sent.set()

    class _MotorPublisher:
        async def send(self, data):
            motor_messages.append(data)
            motor_sent.set()

    @asynccontextmanager
    async def _display_pub_ctx(_pub_opt):
        yield _DisplayPublisher()

    @asynccontextmanager
    async def _motor_pub_ctx(_pub_opt):
        yield _MotorPublisher()

    display_pub_opt = object()
    motor_pub_opt = object()

    def _fake_get_async_publisher(pub_opt):
        if pub_opt is display_pub_opt:
            return _display_pub_ctx(pub_opt)
        if pub_opt is motor_pub_opt:
            return _motor_pub_ctx(pub_opt)
        raise AssertionError("unexpected publisher option")

    monkeypatch.setattr(display_target.msg_handler, "get_async_publisher", _fake_get_async_publisher)
    monkeypatch.setattr(motor_target.msg_handler, "get_async_publisher", _fake_get_async_publisher)
    monkeypatch.setattr(
        display_target.msg_handler,
        "DisplayMessage",
        lambda **kwargs: SimpleNamespace(**kwargs),
    )
    monkeypatch.setattr(
        motor_target.msg_handler,
        "MotorState",
        SimpleNamespace(DEPLOYING="DEPLOYING", FOLDING="FOLDING"),
    )
    monkeypatch.setattr(
        motor_target.msg_handler,
        "MotorMessage",
        lambda **kwargs: SimpleNamespace(**kwargs),
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
    display_proc = DisplaySenderProcessor(
        state=state,
        state_lock=state_lock,
        signal_sensor_process=signal_display,
        pub_opt=display_pub_opt,
        sender_id="display-center",
    )
    motor_proc = MotorSenderProcessor(
        state=state,
        state_lock=state_lock,
        derived_state=derived_state,
        derived_state_lock=derived_state_lock,
        signal_motor_process=signal_motor,
        pub_opt=motor_pub_opt,
        sender_id="motor-center",
        loop_time=60.0,
    )

    sensor_task = asyncio.create_task(sensor_proc.run())
    display_task = asyncio.create_task(display_proc.run())
    motor_task = asyncio.create_task(motor_proc.run())

    class _OverrideMsg:
        def __init__(self):
            self.sender_id = "override_1"
            self.sender_name = "override"
            self.timestamp = datetime.now()
            self.payload = recv_target.msg_handler.schemas.HeartBeatPayload(
                status="override",
                status_code=200,
            )

        def get_status(self):
            return self.payload.status_code, self.payload.status

    override_msg = _OverrideMsg()
    await recv._override_button(override_msg)
    signal_sensor.publish()

    await asyncio.wait_for(display_sent.wait(), timeout=1.0)
    await asyncio.wait_for(motor_sent.wait(), timeout=1.0)

    assert state.isin_override_mode is True
    assert display_messages[-1].is_override_mode is True
    assert motor_messages[-1].is_override_mode is True
    assert motor_messages[-1].ordered_mode == "FOLDING"

    for task in (sensor_task, display_task, motor_task):
        task.cancel()

    for task in (sensor_task, display_task, motor_task):
        with pytest.raises(asyncio.CancelledError):
            await task
