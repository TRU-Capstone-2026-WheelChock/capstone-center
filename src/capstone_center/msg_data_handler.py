# src/capstone-center/msg_data_processor.py
import os
import asyncio
import msg_handler
import logging
from datetime import timedelta, datetime


class MessageDataProcessor:
    def __init__(self, shared_list : list[msg_handler.SensorMessage]|None = None, purge_time : float = float(os.getenv("PURGE_MIN", "10")), loop_time: float =60.0):
        self.shared_list = shared_list if shared_list is not None else []
        self.purge_time = purge_time
        self.loop_time = loop_time


    async def heart_beat(self):
        pass

    async def purge_data(self):
        now = datetime.now()
        threshold = timedelta(minutes=self.purge_time)
        self.shared_list[:] = [
            msg for msg in self.shared_list
            if (now - msg.timestamp) <= threshold
        ]
            
    async def process_data(self, loop_time : float|None = None):
        loop_time = loop_time or self.loop_time
        while True:
            await asyncio.sleep(loop_time)
            await self.purge_data()
    
