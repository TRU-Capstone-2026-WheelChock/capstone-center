import asyncio
import logging

import msg_handler
from pydantic import ValidationError

from capstone_center.decorators import with_state_lock
from capstone_center.state_store import RuntimeState, CoalescedUpdateSignal


class DisplaySenderProcessor():
    def __init__(
        self,
        state: RuntimeState,
        state_lock: asyncio.Lock,
        signal_sensor_process :CoalescedUpdateSignal,
        pub_opt: msg_handler.ZmqPubOptions,
        logger: logging.Logger | None = None,
        sender_id : str = "1"
    ):
        self.state = state
        self.state_lock = state_lock
        self.pub_opt = pub_opt
        self.signal_sensor_process = signal_sensor_process
        self.sender_id = sender_id
        self.logger = logger or logging.getLogger(__name__)

    @with_state_lock
    async def _build_display_message(self) -> msg_handler.DisplayMessage:
        return msg_handler.DisplayMessage(
            sender_id=self.sender_id,
            is_override_mode=self.state.isin_override_mode,
            sensor_display_dict=self.state.get_alive_latest_display_dict(),
            moter_mode=self.state.motor_mode,
        )

    async def run(self):
        async with msg_handler.get_async_publisher(self.pub_opt) as pub:
            self.logger.info("display publisher is UP")
            while True:
                await self.signal_sensor_process.wait_next()
                try:
                    data = await self._build_display_message()
                    await pub.send(data)
                    self.logger.debug("display message sent")
                except ValidationError:
                    self.logger.exception("Drop invalid display message due to validation error")
                except Exception:
                    self.logger.exception("Unexpected error while sending display message.")
