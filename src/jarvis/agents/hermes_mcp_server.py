import json
from pathlib import Path
from typing import Any

import httpx
from mcp.server import MCPServer

from jarvis.agents.hermes_bridge import (
    hermes_bridge_state_path,
)

mcp = MCPServer(
    "JARVIS Trusted Tools"
)


class JarvisBridgeUnavailableError(
    RuntimeError
):
    """
    Raised when the running JARVIS desktop bridge cannot be
    reached.
    """


class JarvisToolExecutionError(
    RuntimeError
):
    """
    Raised when the trusted JARVIS bridge rejects or fails a
    requested tool action.
    """


def _load_bridge_state() -> tuple[
    str,
    str,
]:
    path: Path = (
        hermes_bridge_state_path()
    )

    try:
        payload = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

    except (
        FileNotFoundError,
        json.JSONDecodeError,
        OSError,
    ) as exc:
        raise JarvisBridgeUnavailableError(
            "The trusted JARVIS desktop bridge "
            "is not currently running."
        ) from exc

    if not isinstance(
        payload,
        dict,
    ):
        raise JarvisBridgeUnavailableError(
            "The JARVIS bridge state is invalid."
        )

    url = payload.get(
        "url"
    )

    token = payload.get(
        "token"
    )

    if not isinstance(
        url,
        str,
    ):
        raise JarvisBridgeUnavailableError(
            "The JARVIS bridge URL is invalid."
        )

    if not isinstance(
        token,
        str,
    ):
        raise JarvisBridgeUnavailableError(
            "The JARVIS bridge token is invalid."
        )

    return (
        url,
        token,
    )


def _bridge_request(
    path: str,
    payload: dict[
        str,
        object,
    ],
) -> object:
    url, token = (
        _load_bridge_state()
    )

    try:
        response = httpx.post(
            f"{url}{path}",
            json=payload,
            headers={
                "Authorization": (
                    f"Bearer {token}"
                ),
            },
            timeout=120,
            trust_env=False,
        )

    except httpx.HTTPError as exc:
        raise JarvisBridgeUnavailableError(
            "Could not communicate with the "
            "trusted JARVIS desktop bridge."
        ) from exc

    try:
        body = response.json()

    except ValueError as exc:
        raise JarvisBridgeUnavailableError(
            "The JARVIS bridge returned an "
            "invalid response."
        ) from exc

    if response.is_error:
        if isinstance(
            body,
            dict,
        ):
            error = body.get(
                "error"
            )

            if isinstance(
                error,
                dict,
            ):
                message = error.get(
                    "message"
                )

                if isinstance(
                    message,
                    str,
                ):
                    raise JarvisToolExecutionError(
                        message
                    )

            if isinstance(
                error,
                str,
            ):
                raise JarvisToolExecutionError(
                    error
                )

        raise JarvisToolExecutionError(
            "The requested JARVIS action failed."
        )

    return body


@mcp.tool()
def list_jarvis_tools() -> object:
    """
    List the trusted Windows-control tools currently exposed by
    JARVIS.

    Call this before executing a JARVIS tool when you need the
    exact tool name or argument schema.

    Only tools explicitly allowlisted by the trusted JARVIS
    core appear here.
    """

    return _bridge_request(
        "/tools",
        {},
    )


@mcp.tool()
def execute_jarvis_tool(
    tool_name: str,
    arguments: dict[
        str,
        Any,
    ],
) -> object:
    """
    Execute one trusted JARVIS tool.

    Use list_jarvis_tools first to obtain the exact tool name
    and argument schema.

    Never invent argument names.

    This function never bypasses JARVIS security.

    Every action returns to the running trusted JARVIS process,
    where PermissionPolicy, capability checks and human
    confirmation remain authoritative.
    """

    return _bridge_request(
        "/execute",
        {
            "tool_name": tool_name,
            "arguments": arguments,
        },
    )


def main() -> None:
    """
    Start the local stdio MCP server.

    Hermes owns this subprocess lifecycle.
    """

    mcp.run(
        transport="stdio"
    )


if __name__ == "__main__":
    main()