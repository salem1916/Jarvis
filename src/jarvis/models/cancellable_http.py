"""Sync-facing HTTP bridge with cancellable asynchronous network I/O."""
import asyncio
from concurrent.futures import TimeoutError as FutureTimeout
from contextlib import contextmanager
from threading import Event, Thread
from typing import Any

import httpx

from jarvis.core.request_control import check_cancelled


class CancellableClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.loop = None
        self.client = None
        self.thread = None

    def __enter__(self):
        ready = Event()
        def run():
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            ready.set()
            self.loop.run_forever()
            self.loop.close()
        self.thread = Thread(target=run, name="jarvis-http", daemon=True)
        self.thread.start()
        ready.wait(5)
        self.client = httpx.AsyncClient(**self.kwargs)
        return self

    def wait(self, coroutine, *, cleanup=False):
        assert self.loop is not None
        operation: asyncio.Future[Any] | None = None
        async def perform():
            nonlocal operation
            task = asyncio.ensure_future(coroutine)
            operation = task
            return await task
        future = asyncio.run_coroutine_threadsafe(perform(), self.loop)
        try:
            while True:
                if not cleanup:
                    check_cancelled()
                try:
                    return future.result(timeout=0.05 if not cleanup else 3)
                except FutureTimeout:
                    if future.done() or cleanup:
                        raise
        finally:
            if not future.done():
                # Cancelling the thread-facing Future alone returns before its
                # async reader unwinds. Drain that reader before closing its
                # generator/response, or Stop can fail with "already running".
                async def cancel_and_drain():
                    if operation is not None:
                        operation.cancel()
                        await asyncio.gather(operation, return_exceptions=True)
                drain = asyncio.run_coroutine_threadsafe(cancel_and_drain(), self.loop)
                try:
                    drain.result(timeout=3)
                except FutureTimeout:
                    drain.cancel()
                finally:
                    future.cancel()

    def post(self, url, **kwargs):
        assert self.client is not None
        return self.wait(self.client.post(url, **kwargs))

    @contextmanager
    def stream(self, method, url, **kwargs):
        assert self.client is not None
        request = self.client.build_request(method, url, **kwargs)
        response = self.wait(self.client.send(request, stream=True))
        owner = self
        class Stream:
            status_code = response.status_code
            headers = response.headers
            def raise_for_status(self):
                return response.raise_for_status()
            def iter_lines(self):
                lines = response.aiter_lines()
                try:
                    while True:
                        try:
                            yield owner.wait(anext(lines))
                        except StopAsyncIteration:
                            return
                finally:
                    owner.wait(lines.aclose(), cleanup=True)
        try:
            yield Stream()
        finally:
            self.wait(response.aclose(), cleanup=True)

    def __exit__(self, *args):
        try:
            if self.client is not None:
                self.wait(self.client.aclose(), cleanup=True)
                assert self.loop is not None
                self.wait(self.loop.shutdown_asyncgens(), cleanup=True)
        finally:
            if self.loop is not None:
                self.loop.call_soon_threadsafe(self.loop.stop)
            if self.thread is not None:
                self.thread.join(timeout=3)


def provider_client(*, transport=None, **kwargs) -> Any:
    # Deterministic test transports need no network cancellation bridge.
    return httpx.Client(transport=transport, **kwargs) if transport is not None else CancellableClient(**kwargs)
