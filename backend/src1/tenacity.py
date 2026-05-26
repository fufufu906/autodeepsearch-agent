from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


@dataclass(frozen=True)
class _StopAfterAttempt:
    attempts: int


@dataclass(frozen=True)
class _WaitExponential:
    multiplier: float = 1.0
    min: float = 0.0
    max: float | None = None

    def delay(self, attempt_number: int) -> float:
        delay = self.multiplier * (2 ** max(attempt_number - 1, 0))
        delay = max(self.min, delay)
        if self.max is not None:
            delay = min(self.max, delay)
        return delay


@dataclass(frozen=True)
class _RetryIfExceptionType:
    exception_types: tuple[type[BaseException], ...]

    def matches(self, exc: BaseException) -> bool:
        return isinstance(exc, self.exception_types)


@dataclass(frozen=True)
class _RetryState:
    attempt_number: int


def stop_after_attempt(attempts: int) -> _StopAfterAttempt:
    return _StopAfterAttempt(attempts=attempts)


def wait_exponential(*, multiplier: float = 1.0, min: float = 0.0, max: float | None = None) -> _WaitExponential:
    return _WaitExponential(multiplier=multiplier, min=min, max=max)


def retry_if_exception_type(*exception_types: type[BaseException] | tuple[type[BaseException], ...]) -> _RetryIfExceptionType:
    flattened: list[type[BaseException]] = []
    for item in exception_types:
        if isinstance(item, tuple):
            flattened.extend(item)
        else:
            flattened.append(item)
    return _RetryIfExceptionType(tuple(flattened) or (Exception,))


def retry(
    *,
    stop: _StopAfterAttempt,
    wait: _WaitExponential | None = None,
    retry: _RetryIfExceptionType | None = None,
    before_sleep: Callable[[Any], Any] | None = None,
):
    def decorator(func: F) -> F:
        def wrapper(*args: Any, **kwargs: Any):
            last_exc: BaseException | None = None
            for attempt_number in range(1, stop.attempts + 1):
                try:
                    return func(*args, **kwargs)
                except BaseException as exc:
                    last_exc = exc
                    if retry is not None and not retry.matches(exc):
                        raise
                    if attempt_number >= stop.attempts:
                        raise
                    if before_sleep is not None:
                        try:
                            before_sleep(_RetryState(attempt_number=attempt_number))
                        except Exception:
                            pass
                    if wait is not None:
                        time.sleep(wait.delay(attempt_number))
            assert last_exc is not None
            raise last_exc

        return wrapper  # type: ignore[return-value]

    return decorator

