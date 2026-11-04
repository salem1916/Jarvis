"""Per-request streaming and cooperative cancellation, isolated across worker threads."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from threading import Event

from jarvis.core.interaction import AssistantEvent


class RequestCancelledError(RuntimeError):
    pass


@dataclass
class RetryBudget:
    used: int = 0
    limit: int = 2


@dataclass
class RequestControl:
    on_delta: Callable[[str], None] | None = None
    on_status: Callable[[str], None] | None = None
    cancelled: Event = field(default_factory=Event)
    started: float = field(default_factory=time.perf_counter)
    first_text_seconds: float | None = None
    retry_budget: RetryBudget = field(default_factory=RetryBudget)
    on_event: Callable[[AssistantEvent], None] | None = None
    events: list[AssistantEvent] = field(default_factory=list)
    input_source: str = "text"
    paused: Event = field(default_factory=Event)

    def check(self) -> None:
        while self.paused.is_set() and not self.cancelled.is_set():
            self.cancelled.wait(0.025)
        if self.cancelled.is_set():
            raise RequestCancelledError("Request stopped. No further actions will be started.")

    def emit(self, text: str) -> None:
        self.check()
        if text and self.first_text_seconds is None:
            self.first_text_seconds = time.perf_counter() - self.started
        if text and self.on_delta:
            self.on_delta(text)


_CURRENT: ContextVar[RequestControl | None] = ContextVar("jarvis_request", default=None)


def current_control() -> RequestControl | None:
    return _CURRENT.get()


def check_cancelled() -> None:
    control = current_control()
    if control:
        control.check()


@contextmanager
def request_scope(control: RequestControl) -> Iterator[None]:
    token = _CURRENT.set(control)
    try:
        control.check()
        yield
    finally:
        _CURRENT.reset(token)


def report_status(text: str) -> None:
    control = current_control()
    if control:
        control.check()
        if control.on_status:
            control.on_status(text)


def report_event(event: AssistantEvent) -> None:
    control = current_control()
    if control:
        control.events.append(event)
        if control.on_event:
            control.on_event(event)
