import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
import logging
import pytest


from msg_handler import (
    get_publisher,
    get_subscriber,
    get_async_subscriber,
    ZmqPubOptions,
    ZmqSubOptions,
    SensorMessage,
    SensorPayload,
    HeartBeatPayload
)

from .helpers import HbState

log = logging.getLogger(__name__)

async def aiter_msgs_from_scenario(sender_id = 0, sender_name = "sender_01", data_type = "test", *, scenarios : list[HbState]) -> AsyncIterator[SensorMessage]:
    msgs : list[SensorMessage]  =[]
    for s in scenarios:
        await asyncio.sleep(s.delay)
        msg = SensorMessage(
                sender_id= sender_id,
                sender_name=sender_name,
                data_type=data_type,
                payload=HeartBeatPayload(
                )
            )
        yield msg



endpoint = "tcp://127.0.0.1:5551"

async def run_pub_hb(endpoint = endpoint, sender_id = 0, sender_name = "sender_01", data_type = "test", *, scenarios : list[HbState]):
    pub_opt = ZmqPubOptions(endpoint)
    with get_publisher(pub_opt) as pub:
        await asyncio.sleep(0.1) # wait for first setup
        for msg in aiter_msgs_from_scenario(sender_id=sender_id, sender_name=sender_name, data_type=data_type, scenarios=scenarios):
            log.debug(f"send information: " + msg)
            pub.send(msg)
            
        


@pytest.mark.asyncio
async def test_heart_beat_single_test():

    assert True


