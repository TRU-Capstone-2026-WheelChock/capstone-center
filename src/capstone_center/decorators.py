"""Decorator utilities shared across capstone_center modules.

Section:
    `with_state_lock` is intended for async instance methods.
    It expects the instance (`self`) to expose `state_lock` that can be used
    as an async context manager (for example, `asyncio.Lock`).
"""

from functools import wraps
from typing import Awaitable, Callable, ParamSpec, TypeVar, Concatenate, Any

P = ParamSpec("P")
R = TypeVar("R")

def with_state_lock(
    fn: Callable[Concatenate[Any, P], Awaitable[R]],
) -> Callable[Concatenate[Any, P], Awaitable[R]]:
    """Serialize async instance-method access using `self.state_lock`.

    Notes:
        - This decorator is for class instance methods, not free functions.
        - The decorated object's `self` must define `state_lock`.
    """

    @wraps(fn)
    async def wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
        lock = getattr(self, "state_lock", None)
        if lock is None:
            raise AttributeError(
                f"{type(self).__name__}.{fn.__name__} requires 'self.state_lock'. "
                "with_state_lock is for async instance methods."
            )
        if not hasattr(lock, "__aenter__") or not hasattr(lock, "__aexit__"):
            raise TypeError(
                f"{type(self).__name__}.state_lock must support async context manager protocol."
            )

        async with lock:
            return await fn(self, *args, **kwargs)
    return wrapper
