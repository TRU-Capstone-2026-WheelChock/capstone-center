from dataclasses import dataclass

@dataclass(frozen=True) #use dataclass here, not pydantic for simplicity.
class HbState:
    status : str
    status_code: int = 200
    
    delay: float = 2.0
    note : str | None = None
