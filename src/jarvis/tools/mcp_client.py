"""Reusable, bounded local MCP connection. Tool discovery grants no authority."""
from __future__ import annotations

import asyncio
import os
import time
from concurrent.futures import Future
from concurrent.futures import TimeoutError as FutureTimeout
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Any

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from jarvis.core.request_control import check_cancelled


def local_environment(extra=None):
    allowed = {"PATH","SYSTEMROOT","WINDIR","TEMP","TMP","USERPROFILE","LOCALAPPDATA","APPDATA","COMSPEC"}
    return {**{k:v for k,v in os.environ.items() if k.upper() in allowed},**(extra or {})}


class StdioMCPClient:
    """One persistent server, one serialized queue, cooperative cancellation."""
    def __init__(self, name, allowed_tools, *, command="", args=(), env=None, root=None, timeout=30):
        self.name = name
        self.allowed_tools = frozenset(allowed_tools)
        self.command,self.args,self.env = command,list(args),env or {}
        self.root = Path(root or Path(__file__).resolve().parents[3])
        self.timeout = timeout
        self.loop: Any = None
        self.queue: Any = None
        self.thread: Thread | None = None
        self.ready = Event()
        self.error = ""
        self.tools: list[str] = []
        self.schemas: dict[str,dict] = {}
        self._lock = Lock()
        self._pending: set[Future] = set()

    def launch(self):
        if not self.command:raise ValueError(f"{self.name} is not installed. Open Settings → Integrations.")
        return StdioServerParameters(command=self.command,args=self.args,env=local_environment(self.env),cwd=str(self.root))

    def decode_result(self, value):
        text = "\n".join(c.text for c in value.content if getattr(c,"type","") == "text")
        if getattr(value,"is_error",getattr(value,"isError",False)) or text.lstrip().startswith(("### Error","Error ","Error:","Error capturing")):
            detail = text.split("Browser logs:",1)[0].replace("### Error","").strip()
            raise ValueError(f"{self.name} operation failed: " + detail[:450])
        return {"text":text,"images":[c.data for c in value.content if getattr(c,"type","") == "image"]}

    async def _serve(self):
        params = self.launch()
        output = self.root/".mcp";output.mkdir(parents=True,exist_ok=True)
        with (output/f"{self.name}-server.log").open("a",encoding="utf-8") as log:
            async with stdio_client(params,errlog=log) as (read,write),ClientSession(read,write) as session:
                await asyncio.wait_for(session.initialize(),timeout=self.timeout)
                listed = await session.list_tools()
                self.schemas = {t.name:getattr(t,"input_schema",None) or getattr(t,"inputSchema",{}) for t in listed.tools if t.name in self.allowed_tools}
                self.tools = list(self.schemas)
                if not self.tools:raise ValueError("No approved tools were advertised.")
                self.ready.set()
                while True:
                    item = await self.queue.get()
                    if item is None:break
                    name,arguments,result = item
                    if result.cancelled():continue
                    task = asyncio.create_task(session.call_tool(name,arguments,read_timeout_seconds=self.timeout))
                    def cancelled(future,call=task):
                        if future.cancelled() and not self.loop.is_closed():self.loop.call_soon_threadsafe(call.cancel)
                    result.add_done_callback(cancelled)
                    try:
                        value = await asyncio.wait_for(task,timeout=self.timeout+1)
                        parsed = self.decode_result(value)
                        if not result.done():result.set_result(parsed)
                    except asyncio.CancelledError:
                        if not result.done():result.cancel()
                    except Exception as exc:  # noqa: BLE001 -- contain one plugin operation
                        if not result.done():result.set_exception(ValueError(str(exc) if isinstance(exc,ValueError) else f"{self.name} did not finish the operation. Observe before retrying."))

    def _start(self):
        with self._lock:
            if self.thread is None or not self.thread.is_alive():
                self.ready.clear();self.error = "";self.tools = []
                def run():
                    self.loop = asyncio.new_event_loop();asyncio.set_event_loop(self.loop);self.queue = asyncio.Queue()
                    try:self.loop.run_until_complete(self._serve())
                    except Exception as exc:  # noqa: BLE001 -- safe connection diagnostics
                        self.error = str(exc) if isinstance(exc,ValueError) else f"{self.name} could not connect. Check Settings → Integrations and its local server log."
                    finally:
                        self.ready.set()
                        for future in tuple(self._pending):
                            if not future.done():future.set_exception(ValueError(f"{self.name} connection closed. No action will be retried automatically."))
                        self.loop.run_until_complete(self.loop.shutdown_asyncgens());self.loop.close()
                self.thread = Thread(target=run,name=f"jarvis-{self.name}-mcp",daemon=True);self.thread.start()
        deadline = time.monotonic()+self.timeout
        while time.monotonic()<deadline:
            check_cancelled()
            if self.ready.wait(0.05):
                if self.error:raise ValueError(self.error)
                return
        raise ValueError(f"{self.name} connection timed out. Check its setup and try again.")

    def connect(self):
        self._start();return list(self.tools)

    def call(self,name,arguments):
        if name not in self.allowed_tools:raise ValueError("This MCP tool is not exposed by JARVIS.")
        self._start()
        if name not in self.tools:raise ValueError("The MCP server did not advertise this tool.")
        result: Future = Future();self._pending.add(result)
        deadline = time.monotonic()+self.timeout+2
        self.loop.call_soon_threadsafe(self.queue.put_nowait,(name,arguments,result))
        try:
            while True:
                check_cancelled()
                try:return result.result(timeout=0.05)
                except FutureTimeout:
                    if result.done():raise
                    if time.monotonic()>deadline:raise ValueError(f"{self.name} wait limit reached. Check the app before retrying; an action may have completed.") from None
        finally:
            if not result.done():result.cancel()
            self._pending.discard(result)

    def close(self):
        if self.thread and self.loop and self.thread.is_alive() and not self.loop.is_closed():
            for future in tuple(self._pending):future.cancel()
            self.loop.call_soon_threadsafe(self.queue.put_nowait,None)
            self.thread.join(timeout=10)
            if self.thread.is_alive():return
        self.thread = None
