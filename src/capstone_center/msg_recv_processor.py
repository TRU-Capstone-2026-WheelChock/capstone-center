# src/capstone-center/msg_recv_processor.py
import asyncio
import msg_handler
import logging


class MessageRecvProcessor:
    def __init__(self, shared_list : list[msg_handler.SensorMessage]):
        self.shared_list = shared_list

    async def handle_heart_beat(self, msg: msg_handler.SensorMessage) -> None:
        print("HB:", msg.sender_id, msg.payload)
        self.shared_list.append(msg)

    async def handle_sensor_status(self, msg: msg_handler.SensorMessage) -> None:
        print("SENSOR:", msg.sender_id, msg.payload)
        self.shared_list.append(msg)

    async def run_subscriber(self, sub_opt: msg_handler.ZmqSubOptions) -> None:
        async with msg_handler.get_async_subscriber(sub_opt) as sub:
            async for raw in sub:
                msg = msg_handler.SensorMessage.model_validate(raw)

                if msg.data_type == "heartbeat":
                    await self.handle_heart_beat(msg)
                elif msg.data_type == "sensor":
                    await self.handle_sensor_status(msg)
                else:
                    print("Unknown data_type:", msg.data_type)

    
