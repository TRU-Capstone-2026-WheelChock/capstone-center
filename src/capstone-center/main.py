# src/your_module/main.py
import os
import asyncio
import msg_handler
import logging
from logging.handlers import RotatingFileHandler
from .config import LOG_FORMAT

level_name = os.getenv("LOGGER_LEVEL", "INFO").upper()
level = getattr(logging, level_name, logging.INFO)
logging.basicConfig(level=level format=LOG_FORMAT)



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



async def main() -> None:
    sub_opt = get_opt()
    # await run_subscriber(sub_opt)

if __name__ == "__main__":
    asyncio.run(main())
    handler = RotatingFileHandler(
    "app.log",
    maxBytes=5 * 1024 * 1024,
    backupCount=10 
        )       



