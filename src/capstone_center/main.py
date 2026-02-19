# src/your_module/main.py
import os
import asyncio
import msg_handler
import logging

from capstone_center.config import LOG_FORMAT

from capstone_center.msg_recv_processor import MessageRecvProcessor
from capstone_center.state_store import RuntimeState, SensorPresence, ComponentHealth


level_name = os.getenv("LOGGER_LEVEL", "INFO").upper()
level = getattr(logging, level_name, logging.INFO)
logging.basicConfig(level=level, format=LOG_FORMAT)
logger = logging.getLogger(__name__)



def get_opt() -> msg_handler.ZmqSubOptions:
    endpoint = os.getenv("ZMQ_SUB_ENDPOINT", "tcp://localhost:5555")
    topics_raw = os.getenv("ZMQ_SUB_TOPICS", "") 
    topics = [t.strip() for t in topics_raw.split(",")] if topics_raw else [""]

    is_bind = os.getenv("ZMQ_SUB_IS_BIND", "true").lower() in ("1", "true", "yes", "y")

    return msg_handler.ZmqSubOptions(
        endpoint=endpoint,
        topics=topics,
        is_bind=is_bind,
    )



class CenterSubscriber:
    def __init__(self, msg_recv_processor: MessageRecvProcessor):
        self.msg_recv_processor = msg_recv_processor

    async def run(self, sub_opt: msg_handler.ZmqSubOptions):
        process_task = asyncio.create_task(self.msg_data_processor.process_data())

        try:
            await self.msg_recv_processor.run_subscriber(sub_opt)
        finally:
            process_task.cancel()
            await asyncio.gather(process_task, return_exceptions=True)




if __name__ == "__main__":
    

    state = RuntimeState()
    state_lock = asyncio.Lock()


    msg_recv_processor = MessageRecvProcessor(state, state_lock)

    main_process = CenterSubscriber(msg_recv_processor)
    asyncio.run(main_process.run(get_opt()))
       


