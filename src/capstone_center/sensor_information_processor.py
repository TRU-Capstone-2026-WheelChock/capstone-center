import asyncio
import logging

import msg_handler
from pydantic import ValidationError

from collections import Counter

from capstone_center.decorators import with_state_lock
from capstone_center.state_store import RuntimeState, CoalescedUpdateSignal
import copy

class SensorInformationProcessor():
    def __init__(self,
                 state : RuntimeState,
                 state_lock: asyncio.Lock,
                 signal_sensor_process : CoalescedUpdateSignal):
        self.state = state
        self.state_lock = state_lock
        self.signal_sensor_process = signal_sensor_process


    @with_state_lock
    async def read_state(self)->RuntimeState:
        return copy.deepcopy(self.state)
    
   
    async def find_human_presence(self, snapshot: RuntimeState)->bool:
        
        alive_latest_sensor_data = self.state.get_alive_latest_sensor_data()


        status_counts = Counter(v.present for v in alive_latest_sensor_data.values())

        return status_counts[True] > status_counts[False]
            
            
                
    async def run(self):
        self.signal_sensor_process.wait_next()
        snapshot = self.read_state()
        is_human = await self.find_human_presence(self)



    