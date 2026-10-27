import pytest

from jarvis.security.capabilities import Capability
from jarvis.tools.open_url import OpenUrlTool


def test_open_url_tool_uses_browser_capability() -> None:
    assert (
        OpenUrlTool.required_capability
        is Capability.USE_BROWSER
    )


def test_opens_https_url() -> None:
    opened_urls: list[str] = []

    def opener(
        url: str,
    ) -> bool:
        opened_urls.append(
            url
        )

        return True

    tool = OpenUrlTool(
        opener=opener
    )

    result = tool.execute(
        {
            "url": (
                "https://www.facebook.com/"
            )
        }
    )

    assert opened_urls == [
        "https://www.facebook.com/"
    ]

    assert result == {
        "ok": True,
        "action": "url_opened",
        "url": "https://www.facebook.com/",
    }


def test_opens_http_url() -> None:
    opened_urls: list[str] = []

    def opener(
        url: str,
    ) -> bool:
        opened_urls.append(
            url
        )

        return True

    tool = OpenUrlTool(
        opener=opener
    )

    tool.execute(
        {
            "url": "http://example.com/"
        }
    )

    assert opened_urls == [
        "http://example.com/"
    ]


@pytest.mark.parametrize(
    "url",
    [
        "file:///C:/Windows/System32",
        "javascript:alert(1)",
        "data:text/plain,hello",
    ],
)
def test_rejects_unsafe_url_schemes(
    url: str,
) -> None:
    tool = OpenUrlTool(
        opener=lambda _: True
    )

    with pytest.raises(
        ValueError
    ):
        tool.execute(
            {
                "url": url
            }
        )


def test_rejects_url_without_hostname() -> None:
    tool = OpenUrlTool(
        opener=lambda _: True
    )

    with pytest.raises(
        ValueError
    ):
        tool.execute(
            {
                "url": "https:///missing-host"
            }
        )


def test_rejects_embedded_credentials() -> None:
    tool = OpenUrlTool(
        opener=lambda _: True
    )

    with pytest.raises(
        ValueError
    ):
        tool.execute(
            {
                "url": (
                    "https://user:password@example.com/"
                )
            }
        )


def test_reports_browser_failure() -> None:
    tool = OpenUrlTool(
        opener=lambda _: False
    )

    with pytest.raises(
        OSError
    ):
        tool.execute(
            {
                "url": "https://example.com/"
            }
        )