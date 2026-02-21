import asyncio
import logging

import msg_handler
from pydantic import ValidationError

from capstone_center.decorators import with_state_lock
from capstone_center.state_store import RuntimeState, CoalescedUpdateSignal


class MessageRecvProcessor:
    def __init__(
        self,
        state: RuntimeState,
        state_lock: asyncio.Lock,
        signal_sensor_process :CoalescedUpdateSignal,
        sub_opt: msg_handler.ZmqSubOptions,
        logger: logging.Logger | None = None,
    ):
        self.state = state
        self.state_lock = state_lock
        self.sub_opt = sub_opt
        self.signal_sensor_process = signal_sensor_process
        self.logger = logger or logging.getLogger(__name__)

    async def _handle_heart_beat(self, msg: msg_handler.SensorMessage) -> None:
        self.logger.debug(
            "handling data for heart_beat from component id: %s, name : %s",
            msg.sender_id,
            msg.sender_name,
        )
        self.state.mark_heartbeat(msg.sender_id, msg.timestamp)

    async def _handle_sensor_status(self, msg: msg_handler.SensorMessage) -> None:
        assert isinstance(msg.payload, msg_handler.SensorPayload), (
            f"Expected SensorPayload, got {type(msg.payload).__name__} "
            f"(data_type={msg.data_type}, sender_id={msg.sender_id})"
        )

        self.logger.debug(
            "handling data for sensor from component id: %s, name : %s",
            msg.sender_id,
            msg.sender_name,
        )
        self.state.update_sensor(
            msg.sender_id,
            msg.timestamp,
            msg.payload.isThereHuman,
            msg.payload.human_exist_possibility,
        )

    async def _handle_status(self, msg: msg_handler.SensorMessage) -> None:
        self.logger.debug(
            "handling data for component status from component id: %s, name : %s",
            msg.sender_id,
            msg.sender_name,
        )
        code, status = msg.get_status()
        self.state.update_status(msg.sender_id, msg.timestamp, code, status)

    @with_state_lock
    async def _sensor_msg_handler(self, msg: msg_handler.SensorMessage) -> None:
        await self._handle_heart_beat(msg)
        await self._handle_status(msg)
        await self._handle_sensor_status(msg)

    @with_state_lock
    async def _other_msg_handler(self, msg: msg_handler.SensorMessage) -> None:
        await self._handle_heart_beat(msg)
        await self._handle_status(msg)

    async def run(self) -> None:
        async with msg_handler.get_async_subscriber(self.sub_opt) as sub:
            self.logger.info("subscriber is UP")
            async for raw in sub:
                self.logger.debug("msg received")
                try:
                    msg = msg_handler.SensorMessage.model_validate(raw)
                    self.logger.debug("payload identified as %s", type(msg.payload).__name__)

                    if msg.data_type == "heartbeat":
                        await self._other_msg_handler(msg)
                    elif msg.data_type == "sensor":
                        await self._sensor_msg_handler(msg)
                    else:
                        self.logger.warning("Unknown data_type: %s", msg.data_type)
                    self.signal_sensor_process.publish()
                except ValidationError:
                    self.logger.exception("Drop invalid message due to validation error")
                except AssertionError:
                    self.logger.exception("Drop message due to payload/type mismatch")
                except Exception:
                    self.logger.exception("Unexpected error while processing message")
        self.logger.info("subscriber shutting down")
