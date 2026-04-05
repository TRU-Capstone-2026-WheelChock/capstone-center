import asyncio
import logging
import os
from pathlib import Path
from typing import Any
import zmq
import zmq.asyncio

import msg_handler
import yaml

from capstone_center.heartbeat_process import HeartbeatConfig, HeartbeatProcessor
from capstone_center.msg_recv_processor import MessageRecvProcessor
from capstone_center.state_store import RuntimeState, DerivedState, CoalescedUpdateSignal
from capstone_center.sensor_information_processor import SensorInformationProcessor
from capstone_center.display_sender_processor import DisplaySenderProcessor
from capstone_center.motor_sender_processor import MotorSenderProcessor


def load_config(path: str = "config.yml") -> dict[str, Any]:
    try:
        with Path(path).open("r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
    except FileNotFoundError:
        raise SystemExit(f"config not found: {path}")
    except yaml.YAMLError as e:
        raise SystemExit(f"invalid yaml: {e}")

    if not isinstance(config, dict):
        raise SystemExit("config root must be a mapping")
    return config


def setup_logger(config: dict[str, Any]) -> logging.Logger:
    try:
        level_name = str(config["logging"]["level"]).upper()
        log_format = config["logging"]["format"]
    except KeyError as e:
        raise SystemExit(f"missing required config: logging.{e.args[0]}")

    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise SystemExit(f"invalid logging.level: {level_name}")

    logging.basicConfig(level=level, format=log_format)
    return logging.getLogger(__name__)


def get_opt(
    config: dict[str, Any],
    *,
    endpoint: str | None = None,
    topics: list[str] | None = None,
    is_bind: bool | None = None,
    context : zmq.asyncio.Context
) -> msg_handler.ZmqSubOptions:
    try:
        endpoint_cfg = config["zmq"]["sub"]["endpoint"]
        topics_cfg = config["zmq"]["sub"]["topics"]
        is_bind_cfg = config["zmq"]["sub"]["is_bind"]
    except KeyError as e:
        raise SystemExit(f"missing required config: zmq.sub.{e.args[0]}")

    endpoint_val = endpoint_cfg if endpoint is None else endpoint

    topics_val = topics_cfg if topics is None else topics
    if not isinstance(topics_val, list):
        raise SystemExit("zmq.sub.topics must be list")
    if not all(isinstance(t, str) for t in topics_val):
        raise SystemExit("zmq.sub.topics items must be string")

    is_bind_val = is_bind_cfg if is_bind is None else is_bind
    if not isinstance(is_bind_val, bool):
        raise SystemExit("zmq.sub.is_bind must be bool")

    return msg_handler.ZmqSubOptions(
        endpoint=endpoint_val,
        topics=topics_val,
        is_bind=is_bind_val,
        context=context,
        expected_type="sensor"
    )


def get_disp_pub_opt(
    config: dict[str, Any],
    *,
    endpoint: str | None = None,
    is_bind: bool | None = None,
    context: zmq.asyncio.Context,
) -> msg_handler.ZmqPubOptions:
    try:
        endpoint_cfg = config["display"]["endpoint"]
        is_bind_cfg = config["zmq"]["sub"]["is_bind"]
    except KeyError as e:
        raise SystemExit(f"missing required config for display publisher: {e.args[0]}")

    endpoint_val = endpoint_cfg if endpoint is None else endpoint

    is_bind_val = is_bind_cfg if is_bind is None else is_bind
    if not isinstance(is_bind_val, bool):
        raise SystemExit("zmq.sub.is_bind must be bool")

    return msg_handler.ZmqPubOptions(
        endpoint=endpoint_val,
        context=context,
        is_connect=not is_bind_val,  # opposite of bind
    )


def get_motor_pub_opt(
    config: dict[str, Any],
    *,
    endpoint: str | None = None,
    is_bind: bool | None = None,
    context: zmq.asyncio.Context,
) -> msg_handler.ZmqPubOptions:
    try:
        endpoint_cfg = config["motor"]["endpoint"]
        is_bind_cfg = config["zmq"]["sub"]["is_bind"]
    except KeyError as e:
        raise SystemExit(f"missing required config for motor publisher: {e.args[0]}")

    endpoint_val = endpoint_cfg if endpoint is None else endpoint

    is_bind_val = is_bind_cfg if is_bind is None else is_bind
    if not isinstance(is_bind_val, bool):
        raise SystemExit("zmq.sub.is_bind must be bool")

    return msg_handler.ZmqPubOptions(
        endpoint=endpoint_val,
        context=context,
        is_connect=not is_bind_val,  # opposite of bind
    )

class CenterApp:
    def __init__(
        self,
        recv: MessageRecvProcessor,
        hb: HeartbeatProcessor,
        sp: SensorInformationProcessor,
        dis: DisplaySenderProcessor,
        motor: MotorSenderProcessor,
        logger: logging.Logger | None = None,
    ):
        self.recv = recv
        self.hb = hb
        self.sp = sp
        self.dis = dis
        self.motor = motor
        self.logger = logger or logging.getLogger(__name__)
        

    async def run(self) -> None:
        self.logger.info("start TaskGroup")
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self.recv.run(), name="subscriber")
            tg.create_task(self.hb.run(), name="heartbeat-runner")
            tg.create_task(self.sp.run(), name="sensor-processor")
            tg.create_task(self.dis.run(), name = "display-processor")
            tg.create_task(self.motor.run(), name="motor-processor")


def build_heartbeat_config(config: dict[str, Any]) -> HeartbeatConfig:
    try:
        runtime = config["runtime"]
        return HeartbeatConfig(
            loop_time=float(runtime["watchdog_interval_sec"]),
            timeout_threshold=float(runtime["heartbeat_timeout_sec"]),
            remove_threshold=float(runtime["heartbeat_remove_sec"]),
        )
    except KeyError as e:
        raise SystemExit(f"missing required config: runtime.{e.args[0]}")
    except (TypeError, ValueError):
        raise SystemExit("runtime heartbeat values must be numeric")


def get_center_sender_id(config: dict[str, Any]) -> str:
    app_config = config.get("app", {})
    if isinstance(app_config, dict):
        name = app_config.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return "center"


def main(config_path: str | None = None) -> None:
    resolved = config_path or os.getenv("CENTER_CONFIG_PATH", "config.yml")
    config = load_config(resolved)
    logger = setup_logger(config)

    state = RuntimeState()
    state_lock = asyncio.Lock()

    
    derived_state = DerivedState()
    derived_state_lock = asyncio.Lock()

    
    ctx = zmq.asyncio.Context()

    sub_opt = get_opt(config, context=ctx)
    hb_config = build_heartbeat_config(config)
    center_sender_id = get_center_sender_id(config)

    signal_sensor_process :CoalescedUpdateSignal = CoalescedUpdateSignal(name = "signal_sensor_process")
    signal_lcd: CoalescedUpdateSignal = CoalescedUpdateSignal(name = "signal_lcd")
    signal_motor = CoalescedUpdateSignal(logger, "sensor->motor")

    msg_recv_processor = MessageRecvProcessor(
        state,
        state_lock,
        signal_sensor_process,
        sub_opt,
        logger=logger,
        motor_component_name=str(config.get("motor", {}).get("name", "motor")),
    )
    heartbeat_processor = HeartbeatProcessor(
        state,
        state_lock,
        hb_config=hb_config,
        logger=logger,
    )

    sensor_info_processor = SensorInformationProcessor(
        state=state,
        state_lock=state_lock,
        derived_state=derived_state,
        derived_state_lock=derived_state_lock,
        signal_sensor_process=signal_sensor_process,
        signal_display_process=signal_lcd,
        signal_motor_process=signal_motor,
        logger=logger,
    )

    display_info_sender = DisplaySenderProcessor(
        state,
        state_lock,
        signal_lcd,
        pub_opt=get_disp_pub_opt(config, context=ctx),
        logger=logger,
        sender_id=center_sender_id,
    )

    motor_info_sender = MotorSenderProcessor(
        state=state,
        state_lock=state_lock,
        derived_state=derived_state,
        derived_state_lock=derived_state_lock,
        signal_motor_process=signal_motor,
        pub_opt=get_motor_pub_opt(config, context=ctx),
        logger=logger,
        sender_id=center_sender_id,
        loop_time=float(config["motor"].get("looptime", 10.0)),
    )

    main_process = CenterApp(
        msg_recv_processor,
        heartbeat_processor,
        sensor_info_processor,
        display_info_sender,
        motor_info_sender,
        logger=logger,
    )
    asyncio.run(main_process.run())


if __name__ == "__main__":
    main()
