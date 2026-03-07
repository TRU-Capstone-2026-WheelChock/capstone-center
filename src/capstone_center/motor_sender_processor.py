import asyncio
import logging
from copy import deepcopy
from typing import Protocol

import msg_handler
from pydantic import ValidationError

from capstone_center.decorators import with_async_lock_attr, with_state_lock
from capstone_center.state_store import CoalescedUpdateSignal, DerivedState, RuntimeState


class _AsyncMotorPublisher(Protocol):
    async def send(self, msg: msg_handler.MotorMessage) -> None: ...


class MotorSenderProcessor:
    """Publish the latest motor command on event updates and periodic retries.

    This processor intentionally re-sends the latest command at a fixed interval
    to mitigate PUB/SUB startup timing issues (slow joiner behavior).
    """
    def __init__(
        self,
        state: RuntimeState,
        state_lock: asyncio.Lock,
        derived_state: DerivedState,
        derived_state_lock: asyncio.Lock,
        signal_motor_process: CoalescedUpdateSignal,
        pub_opt: msg_handler.ZmqPubOptions,
        logger: logging.Logger | None = None,
        sender_id: str = "1",
        loop_time : float = 10.0
    ):
        self.state = state
        self.state_lock = state_lock
        self.derived_state = derived_state
        self.derived_state_lock = derived_state_lock
        self.pub_opt = pub_opt
        self.signal_motor_process = signal_motor_process
        self.sender_id = sender_id
        self.logger = logger or logging.getLogger(__name__)
        self.loop_time = loop_time

    @with_state_lock
    async def _get_motor_related_runtime_fields(self) -> tuple[bool, str]:
        """Read only the runtime fields needed for motor command generation."""
        return self.state.isin_override_mode, self.state.motor_mode

    @with_async_lock_attr("derived_state_lock")
    async def _get_derived_state_snapshot(self) -> DerivedState:
        """Take a stable snapshot of the latest derived sensor decision."""
        return deepcopy(self.derived_state)

    def decide_next_motor_state(
        self,
        is_human: bool,
        isin_override_mode: bool,
    ) -> msg_handler.MotorState:
        """Convert the latest decision inputs into a motor command state."""
        if isin_override_mode:
            return msg_handler.MotorState.FOLDING
        if is_human:
            return msg_handler.MotorState.DEPLOYING
        return msg_handler.MotorState.FOLDING

    async def _build_motor_message(
        self,
        isin_override_mode: bool,
        derived_state_snap: DerivedState,
    ) -> msg_handler.MotorMessage:
        """Build one outbound message from runtime and derived snapshots."""
        next_state = self.decide_next_motor_state(
            is_human=derived_state_snap.latest_is_human,
            isin_override_mode=isin_override_mode,
        )

        return msg_handler.MotorMessage(
            sender_id=self.sender_id,
            is_override_mode=isin_override_mode,
            ordered_mode=next_state,
        )

    async def _wait_for_trigger_reason(self) -> str:
        """Return whether the next publish was triggered by an event or timeout."""
        try:
            # Normal path: wake up immediately when sensor processing publishes an update.
            await asyncio.wait_for(self.signal_motor_process.wait_next(), timeout=self.loop_time)
            return "event"
        except asyncio.TimeoutError:
            # Timeout path is intentional. We periodically re-send the latest
            # command so a late subscriber can catch up even if it missed
            # earlier PUB messages.
            return "periodic"

    async def _publish_once(self, pub: _AsyncMotorPublisher, reason: str) -> None:
        """Build and publish the latest motor command once."""
        try:
            self.logger.debug("sending motor command (%s trigger)", reason)
            isin_override_mode, _motor_mode = await self._get_motor_related_runtime_fields()
            derived_state_snap = await self._get_derived_state_snapshot()

            data = await self._build_motor_message(
                isin_override_mode=isin_override_mode,
                derived_state_snap=derived_state_snap,
            )
            await pub.send(data)
            self.logger.debug("motor message sent (%s trigger)", reason)
        except ValidationError:
            self.logger.exception("Drop invalid motor message due to validation error")
        except Exception:
            self.logger.exception("Unexpected error while sending motor message.")

    async def _run_publish_loop(self, pub: _AsyncMotorPublisher) -> None:
        """Keep publishing on update events and periodic retry timeouts."""
        while True:
            reason = await self._wait_for_trigger_reason()
            await self._publish_once(pub, reason)

    async def run(self) -> None:
        """Open the publisher and keep sending motor commands."""
        async with msg_handler.get_async_publisher(self.pub_opt) as pub:
            self.logger.info("motor publisher is UP")
            await self._run_publish_loop(pub)
