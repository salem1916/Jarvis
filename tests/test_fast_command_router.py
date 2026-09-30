from jarvis.core.fast_command_router import FastCommandRouter


def test_routes_open_application() -> None:
    router = FastCommandRouter()

    request = router.route(
        "Open Spotify"
    )

    assert request is not None
    assert request.tool_name == "open_application"
    assert request.arguments == {
        "application": "Spotify",
    }


def test_routes_polite_open_application() -> None:
    router = FastCommandRouter()

    request = router.route(
        "Please open Calculator"
    )

    assert request is not None
    assert request.tool_name == "open_application"
    assert request.arguments == {
        "application": "Calculator",
    }


def test_removes_optional_the_prefix() -> None:
    router = FastCommandRouter()

    request = router.route(
        "Open the Discord"
    )

    assert request is not None
    assert request.arguments == {
        "application": "Discord",
    }


def test_informational_question_does_not_fast_route() -> None:
    router = FastCommandRouter()

    assert router.route(
        "How do I open Spotify?"
    ) is None


def test_multistep_request_does_not_fast_route() -> None:
    router = FastCommandRouter()

    assert router.route(
        "Open Spotify and play music"
    ) is None


def test_file_request_does_not_fast_route() -> None:
    router = FastCommandRouter()

    assert router.route(
        "Open notes.txt"
    ) is None


def test_path_request_does_not_fast_route() -> None:
    router = FastCommandRouter()

    assert router.route(
        r"Open C:\Users\salem\notes.txt"
    ) is None


def test_normal_chat_does_not_fast_route() -> None:
    router = FastCommandRouter()

    assert router.route(
        "Tell me something interesting"
    ) is None