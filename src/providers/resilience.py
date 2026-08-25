"""Yetenek bazlı, thread-safe devre kesici."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Callable


class CircuitOpenError(RuntimeError):
    """Sağlayıcı devresinin açık olduğunu belirtir."""


@dataclass(frozen=True, slots=True)
class CircuitSnapshot:
    state: str
    consecutive_failures: int
    retry_after_seconds: float


class CircuitBreaker:
    """Ardışık hatalarda açılan ve tek half-open probe'a izin veren devre."""

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        open_seconds: float = 30.0,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("failure_threshold pozitif olmalıdır")
        if open_seconds <= 0:
            raise ValueError("open_seconds pozitif olmalıdır")
        self.failure_threshold = failure_threshold
        self.open_seconds = open_seconds
        self._clock = clock
        self._lock = Lock()
        self._failures = 0
        self._opened_at: float | None = None
        self._half_open_in_flight = False

    def acquire(self) -> None:
        """Çağrı izni verir veya devre açıksa güvenli biçimde reddeder."""

        with self._lock:
            if self._opened_at is None:
                return
            elapsed = self._clock() - self._opened_at
            if elapsed < self.open_seconds:
                raise CircuitOpenError("Sağlayıcı devresi geçici olarak açık")
            if self._half_open_in_flight:
                raise CircuitOpenError("Sağlayıcı half-open probe bekliyor")
            self._half_open_in_flight = True

    def success(self) -> None:
        with self._lock:
            self._failures = 0
            self._opened_at = None
            self._half_open_in_flight = False

    def failure(self, *, permanent: bool = False) -> None:
        with self._lock:
            self._failures = self.failure_threshold if permanent else self._failures + 1
            self._half_open_in_flight = False
            if self._failures >= self.failure_threshold:
                self._opened_at = self._clock()

    def snapshot(self) -> CircuitSnapshot:
        with self._lock:
            if self._opened_at is None:
                state = "closed"
                retry_after = 0.0
            else:
                elapsed = self._clock() - self._opened_at
                retry_after = max(0.0, self.open_seconds - elapsed)
                state = "open" if retry_after > 0 else "half_open"
            return CircuitSnapshot(
                state=state,
                consecutive_failures=self._failures,
                retry_after_seconds=round(retry_after, 3),
            )
