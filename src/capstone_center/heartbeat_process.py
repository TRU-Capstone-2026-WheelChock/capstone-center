# src/capstone-center/heartbeat_process.py
import asyncio
import logging
from datetime import datetime
from capstone_center.state_store import RuntimeState
from capstone_center.decorators import with_state_lock

class HeartbeatProcessor():

    def __init__(self, state : RuntimeState, state_lock: asyncio.Lock, logger:logging.Logger|None = None):
        self.state = state
        self.state_lock = state_lock
        self.logger = logger or logging.getLogger(__name__)

    @with_state_lock
    async def heartbeat_process(self, now: datetime,  timeout_threshold : float, remove_threshold: float):
        remove_ids: list[str] = []
        for component_id, hb in self.state.heartbeats.items():
            last = hb.last_seen
            if last is None:
                continue
            elapsed = (now - last).total_seconds()
            if elapsed > timeout_threshold:
                if component_id not in self.state.dead_components_set:
                    self.state.dead_components_set.add(component_id)
                    self.logger.warning(f"Component timeout - id: {component_id}, last_seen: {last}s")
                if elapsed > remove_threshold:
                    remove_ids.append(component_id)
        
        for component_id in remove_ids:
            self.state.heartbeats.pop(component_id, None)
                    

    async def heartbeat_runner(self, loop_time : float, timeout_threshold : float, remove_threshold: float):
        if loop_time <= 0 or timeout_threshold <= 0 or remove_threshold <= 0:
            raise ValueError("loop_time and timeout_threshold must be > 0")
        
        try:
            while True:
                await asyncio.sleep(loop_time)
                now : datetime = datetime.now()
                await self.heartbeat_process(now, timeout_threshold, remove_threshold)
        except asyncio.CancelledError:
            self.logger.info("Heartbeat loop cancelled")
            raise
        
        
