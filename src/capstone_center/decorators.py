"""Decorator utilities shared across capstone_center modules.

Section:
    `with_lock(lock_attr=...)` is a decorator factory for async instance
    methods. It expects the instance (`self`) to expose the named lock
    attribute (for example, `state_lock` or `derived_state_lock`) as an async
    context manager such as `asyncio.Lock`.

    `with_state_lock` is a compatibility alias for `with_lock("state_lock")`.
"""

# src/capstone_center/decorators.py
from functools import wraps
from typing import Awaitable, Callable, ParamSpec, TypeVar, Concatenate, Any

P = ParamSpec("P")
R = TypeVar("R")

def with_async_lock_attr(lock_attr: str = "state_lock"):
    """Build a decorator that serializes async instance methods via a lock.

    Args:
        lock_attr: Name of the lock attribute on `self`.

    Returns:
        A decorator for async instance methods.
    """
    def decorator(
        fn: Callable[Concatenate[Any, P], Awaitable[R]],
    ) -> Callable[Concatenate[Any, P], Awaitable[R]]:
        """Serialize async instance-method access using `self.<lock_attr>`.

        Notes:
            - This decorator is for class instance methods, not free functions.
            - The decorated object's `self` must define the lock named by
              `lock_attr`.
        """
        @wraps(fn)
        async def wrapper(self: Any, *args: P.args, **kwargs: P.kwargs) -> R:
            lock = getattr(self, lock_attr, None)
            if lock is None:
                raise AttributeError(
                    f"{type(self).__name__}.{fn.__name__} requires 'self.{lock_attr}'."
                )
            if not hasattr(lock, "__aenter__") or not hasattr(lock, "__aexit__"):
                raise TypeError(
                    f"{type(self).__name__}.{lock_attr} must support async context manager protocol."
                )
            async with lock:
                return await fn(self, *args, **kwargs)
        return wrapper
    return decorator

# Backward-compatible alias used by existing processors.
with_state_lock = with_async_lock_attr("state_lock")
