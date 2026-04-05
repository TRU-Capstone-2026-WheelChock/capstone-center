import asyncio
import logging
from datetime import datetime

import msg_handler
from pydantic import ValidationError

from zmq import Context

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
        motor_component_name: str = "motor",
    ):
        self.state = state
        self.state_lock = state_lock
        self.sub_opt = sub_opt
        self.signal_sensor_process = signal_sensor_process
        self.logger = logger or logging.getLogger(__name__)
        self.motor_component_name = motor_component_name

    async def _handle_heart_beat(self, msg: msg_handler.SensorMessage) -> None:
        self.logger.debug(
            "handling data for heart_beat from component id: %s, name : %s",
            msg.sender_id,
            msg.sender_name,
        )
        # Use receiver-side time to avoid sender timestamp precision/clock skew issues.
        self.state.mark_heartbeat(msg.sender_id, datetime.now())

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
        motor_state = self._resolve_motor_mode(msg, status)
        if motor_state is not None:
            self.state.set_motor_mode(motor_state)

    def _resolve_motor_mode(
        self,
        msg: msg_handler.SensorMessage,
        status: str,
    ) -> msg_handler.MotorState | None:
        if str(getattr(msg, "data_type", "")) != "heartbeat":
            return None
        if getattr(msg, "sender_name", None) != self.motor_component_name:
            return None
        motor_state_type = msg_handler.MotorState
        try:
            return motor_state_type(status)
        except TypeError:
            if hasattr(motor_state_type, status):
                return getattr(motor_state_type, status)
        except ValueError:
            pass

        self.logger.debug(
            "ignoring non-motor status from motor heartbeat sender=%s status=%r",
            getattr(msg, "sender_id", "<unknown>"),
            status,
        )
        return None

    async def _handle_override(self, msg: msg_handler.SensorMessage)->None:
        if not isinstance(msg.payload, msg_handler.schemas.HeartBeatPayload):
            raise AssertionError("Unacceptable Message type")

        isin_override = False


        if msg.payload.status == "override":
            isin_override = True

        self.state.set_override_mode(isin_override)
            

    @with_state_lock
    async def _sensor_msg_handler(self, msg: msg_handler.SensorMessage) -> None:
        await self._handle_heart_beat(msg)
        await self._handle_status(msg)
        await self._handle_sensor_status(msg)

    @with_state_lock
    async def _other_msg_handler(self, msg: msg_handler.SensorMessage) -> None:
        await self._handle_heart_beat(msg)
        await self._handle_status(msg)

    
    @with_state_lock
    async def _override_button(self, msg: msg_handler.SensorMessage)->None:
        await self._handle_heart_beat(msg)
        await self._handle_status(msg)
        await self._handle_override(msg)



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
                    elif msg.data_type == msg_handler.GenericMessageDatatype.OVERRIDE_BUTTON:
                        await self._override_button(msg)
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
