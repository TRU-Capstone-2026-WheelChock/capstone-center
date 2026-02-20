import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime

from capstone_center.decorators import with_state_lock
from capstone_center.state_store import RuntimeState


@dataclass(frozen=True)
class HeartbeatConfig:
    loop_time: float
    timeout_threshold: float
    remove_threshold: float


class HeartbeatProcessor:
    def __init__(
        self,
        state: RuntimeState,
        state_lock: asyncio.Lock,
        *,
        hb_config: HeartbeatConfig,
        logger: logging.Logger | None = None,
    ):
        self.state = state
        self.state_lock = state_lock
        self.loop_time = hb_config.loop_time
        self.timeout_threshold = hb_config.timeout_threshold
        self.remove_threshold = hb_config.remove_threshold
        self.logger = logger or logging.getLogger(__name__)

    @with_state_lock
    async def heartbeat_process(
        self,
        now: datetime,
        timeout_threshold: float,
        remove_threshold: float,
    ) -> None:
        remove_ids: list[str] = []
        for component_id, hb in self.state.heartbeats.items():
            last = hb.last_seen
            if last is None:
                continue
            elapsed = (now - last).total_seconds()
            if elapsed > timeout_threshold:
                if component_id not in self.state.dead_components_set:
                    self.state.dead_components_set.add(component_id)
                    self.logger.warning(
                        "Component timeout - id: %s, last_seen: %ss",
                        component_id,
                        last,
                    )
                if elapsed > remove_threshold:
                    remove_ids.append(component_id)

        for component_id in remove_ids:
            self.state.heartbeats.pop(component_id, None)

    async def heartbeat_runner(
        self,
        *,
        loop_time: float,
        timeout_threshold: float,
        remove_threshold: float,
    ) -> None:
        if loop_time <= 0 or timeout_threshold <= 0 or remove_threshold <= 0:
            raise ValueError("loop_time and timeout_threshold must be > 0")

        try:
            while True:
                await asyncio.sleep(loop_time)
                await self.heartbeat_process(datetime.now(), timeout_threshold, remove_threshold)
        except asyncio.CancelledError:
            self.logger.info("Heartbeat loop cancelled")
            raise

    async def run(self, *, hb_config: HeartbeatConfig | None = None) -> None:
        cfg = hb_config or HeartbeatConfig(
            loop_time=self.loop_time,
            timeout_threshold=self.timeout_threshold,
            remove_threshold=self.remove_threshold,
        )
        await self.heartbeat_runner(
            loop_time=cfg.loop_time,
            timeout_threshold=cfg.timeout_threshold,
            remove_threshold=cfg.remove_threshold,
        )
