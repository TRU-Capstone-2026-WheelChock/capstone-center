import asyncio

import pytest

from capstone_center.state_store import CoalescedUpdateSignal


@pytest.mark.asyncio
async def test_coalesced_update_signal_wait_next_unblocks_after_publish() -> None:
    """`wait_next()` blocks until `publish()` sets the pending event."""
    signal = CoalescedUpdateSignal(name="unit-test")

    waiter = asyncio.create_task(signal.wait_next())
    await asyncio.sleep(0)

    assert waiter.done() is False

    signal.publish()

    await asyncio.wait_for(waiter, timeout=1.0)


@pytest.mark.asyncio
async def test_coalesced_update_signal_wait_next_clears_after_wakeup() -> None:
    """After one wake-up, `wait_next()` should wait again for the next publish."""
    signal = CoalescedUpdateSignal(name="unit-test")

    signal.publish()
    await signal.wait_next()

    waiter = asyncio.create_task(signal.wait_next())
    await asyncio.sleep(0)

    assert waiter.done() is False

    signal.publish()

    await asyncio.wait_for(waiter, timeout=1.0)


@pytest.mark.asyncio
async def test_coalesced_update_signal_counts_overwrites_while_pending() -> None:
    """Repeated publish calls while pending should increment the overwrite counter."""
    signal = CoalescedUpdateSignal(name="unit-test")

    signal.publish()
    assert signal.stats_count == 0

    signal.publish()
    assert signal.stats_count == 1

    signal.publish()
    assert signal.stats_count == 2

    await signal.wait_next()

    signal.publish()
    assert signal.stats_count == 0
