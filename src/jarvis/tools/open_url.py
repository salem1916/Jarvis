import webbrowser
from collections.abc import Callable, Mapping
from typing import ClassVar
from urllib.parse import urlsplit

from jarvis.security.capabilities import Capability
from jarvis.tools.base import Tool


class OpenUrlTool(Tool):
    """
    Open a safe HTTP or HTTPS URL in the user's default browser.

    This tool deliberately rejects:

        file:// URLs
        javascript: URLs
        data: URLs
        embedded usernames/passwords
        malformed URLs

    The tool does not execute shell commands.
    """

    name = "open_url"

    description = (
        "Open an HTTP or HTTPS website in the user's default "
        "browser. Use this for websites and URLs, not installed "
        "Windows applications."
    )

    required_capability = Capability.USE_BROWSER

    parameters_schema: ClassVar[
        dict[
            str,
            object,
        ]
    ] = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": (
                    "Full HTTP or HTTPS URL to open."
                ),
            },
        },
        "required": [
            "url",
        ],
        "additionalProperties": False,
    }

    def __init__(
        self,
        opener: Callable[[str], bool] | None = None,
    ) -> None:
        self._opener = (
            opener
            if opener is not None
            else self._open_default_browser
        )

    def execute(
        self,
        arguments: Mapping[str, object],
    ) -> object:
        raw_url = arguments.get(
            "url"
        )

        if not isinstance(
            raw_url,
            str,
        ):
            raise TypeError(
                "'url' must be a string."
            )

        url = raw_url.strip()

        if not url:
            raise ValueError(
                "URL cannot be empty."
            )

        if len(url) > 2048:
            raise ValueError(
                "URL is too long."
            )

        if any(
            ord(character) < 32
            for character in url
        ):
            raise ValueError(
                "URL contains invalid control characters."
            )

        parsed = urlsplit(
            url
        )

        if (
            parsed.scheme.casefold()
            not in {
                "http",
                "https",
            }
        ):
            raise ValueError(
                "Only HTTP and HTTPS URLs are allowed."
            )

        if not parsed.hostname:
            raise ValueError(
                "URL must contain a valid hostname."
            )

        if (
            parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError(
                "URLs containing credentials are not allowed."
            )

        try:
            opened = self._opener(
                url
            )

        except OSError as exc:
            raise OSError(
                "Could not open the URL."
            ) from exc

        if not opened:
            raise OSError(
                "The default browser refused to open the URL."
            )

        return {
            "ok": True,
            "action": "url_opened",
            "url": url,
        }

    @staticmethod
    def _open_default_browser(
        url: str,
    ) -> bool:
        return webbrowser.open(
            url,
            new=2,
        )