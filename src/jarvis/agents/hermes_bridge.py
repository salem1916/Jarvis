import json
import os
import secrets
import threading
from http.server import (
    BaseHTTPRequestHandler,
    ThreadingHTTPServer,
)
from pathlib import Path
from typing import Any, Self

from jarvis.core.action_confirmation import (
    ActionConfirmationHandler,
    ActionConfirmationRequest,
    ActionDeclinedError,
)
from jarvis.core.tool_request import ToolRequest
from jarvis.tools.executor import (
    ConfirmationRequiredError,
    PermissionDeniedError,
)
from jarvis.tools.service import ToolService

_ALLOWED_HERMES_TOOLS = frozenset(
    {
        "list_applications",
        "open_application",
        "list_open_windows",
        "control_window",
        "close_window",
        "list_ui_elements",
        "click_ui_element",
        "type_text",
        "keyboard_action",
    }
)


def hermes_bridge_state_path() -> Path:
    """
    Return the discovery file used by the JARVIS MCP
    subprocess to locate the currently running desktop bridge.

    The file contains only:

        localhost URL
        short-lived authentication token
        current process ID

    It never contains model or API credentials.
    """

    base_raw = os.environ.get(
        "LOCALAPPDATA"
    )

    if base_raw:
        base = Path(
            base_raw
        )

    else:
        base = (
            Path.home()
            / ".jarvis"
        )

    return (
        base
        / "Jarvis"
        / "hermes_bridge.json"
    )


class JarvisHermesBridge:
    """
    Temporary loopback bridge between Hermes MCP and the
    currently running trusted JARVIS application.

    Hermes never executes Windows operations directly.

    MCP request
        ↓
    loopback bridge
        ↓
    allowlisted JARVIS ToolRequest
        ↓
    ToolService
        ↓
    PermissionPolicy
        ↓
    human confirmation
        ↓
    ToolExecutor
        ↓
    trusted JARVIS Tool

    The server binds only to 127.0.0.1.

    A random bearer token is generated for every bridge
    lifetime and removed when the bridge stops.
    """

    def __init__(
        self,
        tool_service: ToolService,
        confirmation_handler: (
            ActionConfirmationHandler
            | None
        ) = None,
    ) -> None:
        self.tool_service = tool_service

        self.confirmation_handler = (
            confirmation_handler
        )

        self._token = (
            secrets.token_urlsafe(
                32
            )
        )

        self._server: (
            ThreadingHTTPServer
            | None
        ) = None

        self._thread: (
            threading.Thread
            | None
        ) = None

        self._base_url: (
            str
            | None
        ) = None

    @property
    def base_url(
        self,
    ) -> str:
        if self._base_url is None:
            raise RuntimeError(
                "Hermes bridge is not running."
            )

        return self._base_url

    def start(
        self,
    ) -> None:
        if self._server is not None:
            raise RuntimeError(
                "Hermes bridge is already running."
            )

        bridge = self

        class RequestHandler(
            BaseHTTPRequestHandler
        ):
            def do_POST(
                self,
            ) -> None:
                bridge._handle_request(
                    self
                )

            def log_message(
                self,
                format: str,
                *args: Any,
            ) -> None:
                # Silence HTTP request logging.
                del format
                del args

        server = ThreadingHTTPServer(
            (
                "127.0.0.1",
                0,
            ),
            RequestHandler,
        )

        server.daemon_threads = True

        server_address = (
            server.server_address
        )

        host = str(
            server_address[0]
        )

        port = int(
            server_address[1]
        )

        self._base_url = (
            f"http://{host}:{port}"
        )

        self._server = server

        thread = threading.Thread(
            target=server.serve_forever,
            name="jarvis-hermes-bridge",
            daemon=True,
        )

        self._thread = thread

        self._write_state_file()

        thread.start()

    def stop(
        self,
    ) -> None:
        server = self._server
        thread = self._thread

        self._server = None
        self._thread = None
        self._base_url = None

        if server is not None:
            server.shutdown()
            server.server_close()

        if (
            thread is not None
            and thread.is_alive()
        ):
            thread.join(
                timeout=2
            )

        self._remove_state_file()

    def __enter__(
        self,
    ) -> Self:
        self.start()

        return self

    def __exit__(
        self,
        _exc_type: object,
        _exc_value: object,
        _traceback: object,
    ) -> None:
        self.stop()

    def tool_definitions(
        self,
    ) -> list[
        dict[
            str,
            object,
        ]
    ]:
        """
        Return only the JARVIS tools explicitly approved for
        Hermes orchestration.

        Filesystem, shell, installation, email, deployment and
        other sensitive capabilities are not exposed here.
        """

        definitions: list[
            dict[
                str,
                object,
            ]
        ] = []

        for tool in (
            self.tool_service
            .registry
            .tools()
        ):
            if (
                tool.name
                not in _ALLOWED_HERMES_TOOLS
            ):
                continue

            definitions.append(
                {
                    "name": tool.name,
                    "description": (
                        tool.description
                    ),
                    "parameters": (
                        tool.parameters_schema
                    ),
                    "capability": (
                        tool.required_capability.value
                    ),
                }
            )

        return definitions

    def execute(
        self,
        tool_name: str,
        arguments: dict[
            str,
            object,
        ],
    ) -> object:
        """
        Execute one allowlisted Hermes-requested JARVIS tool.

        Permission checks are never bypassed.
        """

        if (
            tool_name
            not in _ALLOWED_HERMES_TOOLS
        ):
            raise PermissionError(
                "Hermes is not allowed to request "
                f"JARVIS tool '{tool_name}'."
            )

        tool = (
            self.tool_service
            .registry
            .get(
                tool_name
            )
        )

        request = ToolRequest(
            tool_name=tool_name,
            arguments=arguments,
        )

        try:
            return (
                self.tool_service.execute(
                    request
                )
            )

        except ConfirmationRequiredError:
            if self.confirmation_handler is None:
                raise

            confirmation = (
                ActionConfirmationRequest(
                    tool_name=tool_name,
                    capability=(
                        tool.required_capability
                    ),
                    arguments=dict(
                        arguments
                    ),
                )
            )

            approved = (
                self.confirmation_handler
                .confirm(
                    confirmation
                )
            )

            if not approved:
                raise ActionDeclinedError(
                    "The user declined the "
                    "requested action."
                )

            return (
                self.tool_service.execute(
                    request,
                    confirmed=True,
                )
            )

    def _handle_request(
        self,
        handler: BaseHTTPRequestHandler,
    ) -> None:
        if not self._is_authorized(
            handler
        ):
            self._send_json(
                handler,
                401,
                {
                    "ok": False,
                    "error": "unauthorized",
                },
            )

            return

        try:
            payload = self._read_json(
                handler
            )

            if handler.path == "/tools":
                result: object = {
                    "ok": True,
                    "tools": (
                        self.tool_definitions()
                    ),
                }

            elif handler.path == "/execute":
                tool_name = payload.get(
                    "tool_name"
                )

                arguments = payload.get(
                    "arguments",
                    {},
                )

                if not isinstance(
                    tool_name,
                    str,
                ):
                    raise TypeError(
                        "'tool_name' must be a string."
                    )

                if not isinstance(
                    arguments,
                    dict,
                ):
                    raise TypeError(
                        "'arguments' must be an object."
                    )

                result = {
                    "ok": True,
                    "result": self.execute(
                        tool_name,
                        arguments,
                    ),
                }

            else:
                self._send_json(
                    handler,
                    404,
                    {
                        "ok": False,
                        "error": "not_found",
                    },
                )

                return

        except (
            PermissionDeniedError,
            ConfirmationRequiredError,
            ActionDeclinedError,
            PermissionError,
        ) as exc:
            self._send_json(
                handler,
                403,
                {
                    "ok": False,
                    "error": {
                        "type": (
                            type(exc).__name__
                        ),
                        "message": str(
                            exc
                        ),
                    },
                },
            )

            return

        except (
            KeyError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            self._send_json(
                handler,
                400,
                {
                    "ok": False,
                    "error": {
                        "type": (
                            type(exc).__name__
                        ),
                        "message": str(
                            exc
                        ),
                    },
                },
            )

            return

        self._send_json(
            handler,
            200,
            result,
        )

    def _is_authorized(
        self,
        handler: BaseHTTPRequestHandler,
    ) -> bool:
        expected = (
            f"Bearer {self._token}"
        )

        received = (
            handler.headers.get(
                "Authorization"
            )
        )

        return secrets.compare_digest(
            received or "",
            expected,
        )

    @staticmethod
    def _read_json(
        handler: BaseHTTPRequestHandler,
    ) -> dict[
        str,
        Any,
    ]:
        raw_length = (
            handler.headers.get(
                "Content-Length",
                "0",
            )
        )

        length = int(
            raw_length
        )

        if (
            length < 0
            or length > 1_000_000
        ):
            raise ValueError(
                "Invalid bridge request size."
            )

        raw_body = (
            handler.rfile.read(
                length
            )
        )

        if not raw_body:
            return {}

        decoded = json.loads(
            raw_body.decode(
                "utf-8"
            )
        )

        if not isinstance(
            decoded,
            dict,
        ):
            raise TypeError(
                "Bridge request body must be "
                "a JSON object."
            )

        return decoded

    @staticmethod
    def _send_json(
        handler: BaseHTTPRequestHandler,
        status: int,
        payload: object,
    ) -> None:
        raw = json.dumps(
            payload,
            ensure_ascii=False,
            default=str,
        ).encode(
            "utf-8"
        )

        handler.send_response(
            status
        )

        handler.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )

        handler.send_header(
            "Content-Length",
            str(
                len(raw)
            ),
        )

        handler.end_headers()

        handler.wfile.write(
            raw
        )

    def _write_state_file(
        self,
    ) -> None:
        path = (
            hermes_bridge_state_path()
        )

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "url": self.base_url,
            "token": self._token,
            "pid": os.getpid(),
        }

        temporary = (
            path.with_suffix(
                ".tmp"
            )
        )

        temporary.write_text(
            json.dumps(
                payload,
                indent=2,
            ),
            encoding="utf-8",
        )

        os.replace(
            temporary,
            path,
        )

    def _remove_state_file(
        self,
    ) -> None:
        path = (
            hermes_bridge_state_path()
        )

        try:
            current = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            FileNotFoundError,
            json.JSONDecodeError,
            OSError,
        ):
            return

        if not isinstance(
            current,
            dict,
        ):
            return

        if (
            current.get(
                "token"
            )
            != self._token
        ):
            return

        try:
            path.unlink()

        except FileNotFoundError:
            pass