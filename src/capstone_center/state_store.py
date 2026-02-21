# src/capstone_center/state_store.py
"""State models and in-memory stores for center-side runtime data.

This module defines lightweight dataclasses used by receiver and watchdog
tasks to track heartbeat, sensor presence, and status history.
"""
from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
import logging


@dataclass(slots=True)
class SensorSample:
    """One sensor observation at a point in time.

    Attributes:
        ts: Message timestamp.
        present: True when a human is detected.
        probability: Optional confidence value for detection.
    """

    ts: datetime
    present: bool
    probability: float | None = None


@dataclass(slots=True)
class SensorHistory:
    """Fixed-length history of recent sensor observations.

    Attributes:
        maxlen: Maximum number of samples to retain.
        samples: Deque containing most recent samples.
    """

    maxlen: int = 3 #in default, check last 3

    samples: deque[SensorSample] = field(init=False)

    def __post_init__(self) -> None:
        """Initialize deque with the configured maximum length."""
        self.samples = deque(maxlen=self.maxlen)

    def push(self, sample: SensorSample) -> None:
        """Append a sample and evict oldest data when full.

        Args:
            sample: Sensor sample to store.
        """
        self.samples.append(sample)

    def latest(self) -> SensorSample | None:
        """Return the latest sample if present.

        Returns:
            The newest SensorSample, or None when empty.
        """
        return self.samples[-1] if self.samples else None

    def to_list(self) -> list[SensorSample]:
        """Return history as a list in insertion order."""
        return list(self.samples)


@dataclass(slots=True)
class ComponentHeartbeat:
    """Heartbeat metadata for a single component.

    Attributes:
        last_seen: Most recent heartbeat timestamp.
    """

    last_seen: datetime | None = None

@dataclass()
class Status:
    """Status record reported by a component.

    Attributes:
        timestamp: Time when status was reported.
        status_code: Numeric status code.
        status: Human-readable status text.
    """

    timestamp : datetime
    status_code : int
    status : str = ""

@dataclass(slots=True)
class StatusHistory:
    """Fixed-length history of component status records.

    Attributes:
        maxlen: Maximum number of status records to retain.
        status_deque: Deque containing most recent status records.
    """

    maxlen: int = 3 #in default, check last 3

    status_deque: deque[Status] = field(init=False)

    def __post_init__(self) -> None:
        """Initialize deque with the configured maximum length."""
        self.status_deque = deque(maxlen=self.maxlen)

    def push(self, status: Status) -> None:
        """Append one status record.

        Args:
            status: Status object to add.
        """
        self.status_deque.append(status)

    def latest(self) -> Status | None:
        """Return the latest status if present.

        Returns:
            The newest Status, or None when empty.
        """
        return self.status_deque[-1] if self.status_deque else None

    def to_list(self) -> list[Status]:
        """Return status history as a list in insertion order."""
        return list(self.status_deque)

@dataclass
class RuntimeState:
    """Aggregate runtime state shared by async tasks.

    Attributes:
        sensor_histories: Recent sensor observations per sensor ID.
        heartbeats: Last heartbeat time per component ID.
        dead_compoentnts_set: IDs currently considered dead.
        status_history: Recent status records per component ID.
        history_len: Default history length used by stores.
    """

    sensor_histories: dict[str, SensorHistory] = field(default_factory=dict)

    heartbeats: dict[str, ComponentHeartbeat] = field(default_factory=dict)
    dead_components_set: set[str] = field(default_factory=set)

    status_history : dict[str, StatusHistory] = field(default_factory=dict) 

    history_len: int = 3

   

    # ---- Create ----
    def _ensure_sensor(self, sensor_id: str) -> None:
        """Create sensor history entry if missing.

        Args:
            sensor_id: Unique sensor identifier.
        """
        if sensor_id not in self.sensor_histories:
            self.sensor_histories[sensor_id] = SensorHistory()

    def _ensure_component(self, component_id: str) -> None:
        """Create heartbeat entry if missing.

        Args:
            component_id: Unique component identifier.
        """
        if component_id not in self.heartbeats:
            self.heartbeats[component_id] = ComponentHeartbeat()
    
    def _ensure_status(self, component_id:str) ->None:
        """Create status history entry if missing.

        Args:
            component_id: Unique component identifier.
        """
        if component_id not in self.status_history:
            self.status_history[component_id] = StatusHistory()

    # ---- Update ----
    def mark_heartbeat(self, component_id: str, ts: datetime) -> None:
        """Update heartbeat timestamp and clear dead flag.

        Args:
            component_id: Unique component identifier.
            ts: Heartbeat timestamp.
        """
        if component_id in self.dead_components_set:
            self.dead_components_set.discard(component_id)

        self._ensure_component(component_id)
        self.heartbeats[component_id].last_seen = ts

    def update_sensor(
        self,
        sensor_id: str,
        ts: datetime,
        present: bool,
        probability: float | None = None,
    ) -> None:
        """Append a sensor observation for a sensor ID.

        Args:
            sensor_id: Unique sensor identifier.
            ts: Observation timestamp.
            present: Presence decision from the sensor.
            probability: Optional confidence value.
        """
        self._ensure_sensor(sensor_id)
        self.sensor_histories[sensor_id].push(
            SensorSample(ts=ts, present=present, probability=probability)
        )

    def update_status(
            self,
            component_id: str,
            ts: datetime,
            status_code: int,
            status : str
    )->None:
        """Append a status record for a component ID.

        Args:
            component_id: Unique component identifier.
            ts: Status timestamp.
            status_code: Numeric status code.
            status: Human-readable status text.
        """
        self._ensure_status(component_id)
        self.status_history[component_id].push(
            Status(ts, status_code, status)
        )

    # ---- Read helper ----
    def latest_sensor(self, sensor_id: str) -> SensorSample | None:
        """Return latest sensor sample for an ID.

        Args:
            sensor_id: Unique sensor identifier.

        Returns:
            The newest sample for the sensor, or None if missing.
        """
        history = self.sensor_histories.get(sensor_id)
        return history.latest() if history else None


    def get_alive_component(self) -> set[str]:
        """Return component IDs currently considered alive.

        Alive is defined as:
            - present in `heartbeats`
            - not listed in `dead_components_set`
            - having a non-None `last_seen`
        """
        alive_ids = set(self.heartbeats) - self.dead_components_set
        return {
            component_id
            for component_id in alive_ids
            if self.heartbeats[component_id].last_seen is not None
        }
    
    def get_alive_latest_sensor_data(self) -> dict[str, SensorSample]:
        alive_ids = self.get_alive_component()
        out: dict[str, SensorSample] = {}

        for component_id in alive_ids:
            sample = self.latest_sensor(component_id)
            if sample is not None:
                out[component_id] = sample

        return out 
    

############ 




###############  Asyncio status #########################


class CoalescedUpdateSignal:
    """
    Event-based signal with overwrite logging.
    - publish(): set event. if already set, count as overwrite.
    - wait_next(): wait + immediate clear (safe pattern).
    """

    def __init__(self, logger: logging.Logger|None = None, name: str = "update") -> None:
        self._event = asyncio.Event()
        self._logger = logger or logging.getLogger(__name__)
        self._name = name
        self.stats_count = 0

    def publish(self) -> None:
        if self._event.is_set():
            self.stats_count += 1
            self._logger.warning(
                "%s signal overwritten while pending (count=%d)",
                self._name,
                self.stats_count,
            )
        else:
            self.stats_count = 0
        self._event.set()

    async def wait_next(self) -> None:
        await self._event.wait()
        # Important: clear immediately after wake-up.
        # If a new publish() arrives during processing, it will set again.
        self._event.clear()
