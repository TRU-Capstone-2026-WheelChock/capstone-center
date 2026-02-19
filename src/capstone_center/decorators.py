from functools import wraps
from typing import Awaitable, Callable, ParamSpec, TypeVar, Concatenate, Any

P = ParamSpec("P")
R = TypeVar("R")

def with_state_lock(
    fn: Callable[Concatenate[Any, P], Awaitable[R]],
) -> Callable[Concatenate[Any, P], Awaitable[R]]:
    @wraps(fn) #without this, any error happened in here reported as error in wrapper, not the original function name
    async def wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
        async with self.state_lock:
            return await fn(self, *args, **kwargs)
    return wrapper
