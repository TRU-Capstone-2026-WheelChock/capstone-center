# src/your_module/main.py
import os
import asyncio
import msg_handler

def get_opt() -> msg_handler.ZmqSubOptions:
    endpoint = os.getenv("ZMQ_SUB_ENDPOINT", "tcp://localhost:5555")
    topics_raw = os.getenv("ZMQ_SUB_TOPICS", "")  # 例: "hb,sensor"
    topics = [t.strip() for t in topics_raw.split(",")] if topics_raw else [""]

    is_bind = os.getenv("ZMQ_SUB_IS_BIND", "true").lower() in ("1", "true", "yes", "y")

    return msg_handler.ZmqSubOptions(
        endpoint=endpoint,
        topics=topics,
        is_bind=is_bind,
    )

async def handle_heart_beat(msg: msg_handler.SensorMessage) -> None:
    print("HB:", msg.sender_id, msg.payload)

async def handle_sensor_status(msg: msg_handler.SensorMessage) -> None:
    print("SENSOR:", msg.sender_id, msg.payload)

async def run_subscriber(sub_opt: msg_handler.ZmqSubOptions) -> None:
    async with msg_handler.get_async_subscriber(sub_opt) as sub:
        async for raw in sub:
            msg = msg_handler.SensorMessage.model_validate(raw)

            if msg.data_type == "heartbeat":
                await handle_heart_beat(msg)
            elif msg.data_type == "sensor":
                await handle_sensor_status(msg)
            else:
                print("Unknown data_type:", msg.data_type)

async def main() -> None:
    sub_opt = get_opt()
    await run_subscriber(sub_opt)

if __name__ == "__main__":
    asyncio.run(main())



