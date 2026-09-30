import re

from jarvis.core.tool_request import ToolRequest


class FastCommandRouter:
    """
    Deterministic router for extremely simple JARVIS commands.

    The purpose of this router is latency reduction.

    Commands that are simple and unambiguous do not need an
    LLM just to decide which trusted JARVIS tool should run.

    SECURITY:

    This router does NOT execute anything.

    It only converts a safe, recognized natural-language
    command into a ToolRequest.

    Execution still goes through:

        ToolService
            ↓
        PermissionPolicy
            ↓
        ToolExecutor
            ↓
        trusted Tool

    If a request is ambiguous or complex, route() returns None
    and the normal AI agent handles it.
    """

    _OPEN_APPLICATION_PATTERN = re.compile(
        r"^(?:please\s+)?"
        r"(?:open|launch)\s+"
        r"(.+?)"
        r"(?:\s+please)?"
        r"[.!]?$",
        re.IGNORECASE,
    )

    _INFORMATIONAL_PREFIXES = (
        "what ",
        "why ",
        "how ",
        "which ",
        "where ",
        "when ",
        "who ",
        "explain ",
        "describe ",
        "tell me ",
        "can you ",
        "could you ",
        "would you ",
    )

    _CHAIN_WORDS = (
        " and ",
        " then ",
        " after ",
        " before ",
        " while ",
    )

    _FILESYSTEM_WORDS = (
        " file",
        " files",
        " folder",
        " folders",
        " directory",
        " directories",
        " path",
        " document",
    )

    def route(
        self,
        prompt: str,
    ) -> ToolRequest | None:
        """
        Convert one simple command into a trusted structured
        ToolRequest.

        Return None when AI reasoning is more appropriate.
        """

        normalized = " ".join(
            prompt
            .strip()
            .split()
        )

        if not normalized:
            return None

        lowered = normalized.casefold()

        if lowered.startswith(
            self._INFORMATIONAL_PREFIXES
        ):
            return None

        request = self._route_open_application(
            normalized
        )

        if request is not None:
            return request

        return None

    def _route_open_application(
        self,
        prompt: str,
    ) -> ToolRequest | None:
        """
        Recognize only an unambiguous request to launch one
        application.

        Examples:

            Open Spotify
            Launch Discord
            Please open Calculator

        Requests such as:

            Open Spotify and play music
            Open notes.txt
            How do I open Spotify?

        intentionally fall back to the normal agent.
        """

        match = self._OPEN_APPLICATION_PATTERN.fullmatch(
            prompt
        )

        if match is None:
            return None

        application = match.group(
            1
        ).strip()

        if not application:
            return None

        lowered_application = application.casefold()

        # ---------------------------------------------
        # MULTI-STEP / COMPLEX REQUEST
        # ---------------------------------------------

        if any(
            word in f" {lowered_application} "
            for word in self._CHAIN_WORDS
        ):
            return None

        # ---------------------------------------------
        # FILESYSTEM-LIKE REQUEST
        # ---------------------------------------------

        if self._looks_like_filesystem_target(
            lowered_application
        ):
            return None

        # ---------------------------------------------
        # SMALL INPUT SAFETY BOUNDARY
        # ---------------------------------------------

        if len(application) > 100:
            return None

        # Friendly names such as:
        #
        #     "the Spotify"
        #
        # are normalized to:
        #
        #     "Spotify"

        if lowered_application.startswith(
            "the "
        ):
            application = application[
                4:
            ].strip()

        if not application:
            return None

        return ToolRequest(
            tool_name="open_application",
            arguments={
                "application": application,
            },
        )

    @staticmethod
    def _looks_like_filesystem_target(
        target: str,
    ) -> bool:
        """
        Avoid routing obvious file/folder requests through the
        application launcher.
        """

        if "\\" in target:
            return True

        if "/" in target:
            return True

        filesystem_words = (
            "file",
            "files",
            "folder",
            "folders",
            "directory",
            "directories",
            "path",
            "document",
        )

        words = set(
            re.findall(
                r"[a-z0-9_-]+",
                target,
            )
        )

        if words.intersection(
            filesystem_words
        ):
            return True

        # Obvious filename extension:
        #
        #     notes.txt
        #     report.pdf
        #
        # Application names containing periods can still fall
        # back safely to the normal agent.

        return bool(
            re.search(
                r"\.[a-z0-9]{1,8}$",
                target,
                re.IGNORECASE,
            )
        )