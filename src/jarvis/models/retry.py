"""Bounded provider retries without repeating host actions."""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from random import uniform
from threading import Event

from jarvis.core.request_control import (
    RetryBudget,
    check_cancelled,
    current_control,
    report_status,
)
from jarvis.models.base import ModelResponse
from jarvis.models.connection_errors import ProviderConnectionError

_GUARD: ContextVar[Callable[[], None] | None] = ContextVar("jarvis_retry_guard", default=None)


@contextmanager
def retry_guard(before_retry: Callable[[], None]) -> Iterator[None]:
    token = _GUARD.set(before_retry)
    try:
        yield
    finally:
        _GUARD.reset(token)


def wait_before_retry(seconds: float) -> None:
    check_cancelled()
    control = current_control()
    (control.cancelled if control else Event()).wait(seconds)
    check_cancelled()


def reserve_format_retry(budget: RetryBudget) -> bool:
    """Regenerate rejected controller data; never execute failed generation."""
    check_cancelled()
    if budget.used >= budget.limit:
        return False
    guard = _GUARD.get()
    if guard:
        guard()  # Additional requests still respect approval and daily caps.
    budget.used += 1
    report_status(f"Correcting the AI response format ({budget.used}/{budget.limit})…")
    return True


def retry_gemini(operation: Callable[[], ModelResponse]) -> ModelResponse:
    control = current_control()
    budget = control.retry_budget if control else RetryBudget()
    while True:
        check_cancelled()
        try:
            return operation()
        except ProviderConnectionError as error:
            if (error.status_code not in {502, 503, 504} or budget.used >= budget.limit
                    or (control is not None and control.first_text_seconds is not None)
                    or (error.retry_after is not None and error.retry_after > 5)):
                raise
            delay = max(2 ** budget.used + uniform(0, 0.2), error.retry_after or 0)
            budget.used += 1
            report_status(f"Gemini is temporarily unavailable (HTTP {error.status_code}). "
                          f"Retrying in {delay:.1f}s ({budget.used}/{budget.limit})…")
            wait_before_retry(delay)
            check_cancelled()
            guard = _GUARD.get()
            if guard:
                guard()  # Each extra API attempt rechecks approval and the daily cap.
            report_status(f"Retrying Gemini ({budget.used}/{budget.limit})…")
