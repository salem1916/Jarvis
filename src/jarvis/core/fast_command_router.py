import re
from typing import ClassVar
from urllib.parse import urlsplit

from jarvis.core.tool_request import ToolRequest


class FastCommandRouter:
    """
    Deterministic router for extremely simple JARVIS commands.

    It converts high-confidence commands directly into trusted
    ToolRequests without calling an LLM.

    It never executes actions itself.
    """

    _OPEN_TARGET_PATTERN = re.compile(
        r"^(?:please\s+)?"
        r"(?:open|launch|visit|browse(?:\s+to)?|go\s+to)\s+"
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

    _WEBSITE_ALIASES: ClassVar[
        dict[
            str,
            str,
        ]
    ] = {
        "facebook": "https://www.facebook.com/",
        "instagram": "https://www.instagram.com/",
        "youtube": "https://www.youtube.com/",
        "google": "https://www.google.com/",
        "github": "https://github.com/",
        "reddit": "https://www.reddit.com/",
        "linkedin": "https://www.linkedin.com/",
        "x": "https://x.com/",
        "twitter": "https://x.com/",
    }

    def route(
        self,
        prompt: str,
    ) -> ToolRequest | None:
        """
        Convert one simple command into a trusted ToolRequest.

        Ambiguous or complex requests return None and continue
        through the normal AI routing system.
        """

        normalized = " ".join(
            prompt
            .strip()
            .split()
        )

        if not normalized:
            return None

        lowered = normalized.casefold()

        # Polite requests for one explicit action still use the zero-model path.
        polite = re.match(
            r"^(?:can|could|would) you (?:please )?((?:open|launch|visit|browse|go to)\s+.+)$",
            normalized, re.IGNORECASE,
        )
        if polite:
            normalized = polite[1]
            lowered = normalized.casefold()

        if lowered.startswith(
            self._INFORMATIONAL_PREFIXES
        ):
            return None

        return self._route_open_target(
            normalized
        )

    def _route_open_target(
        self,
        prompt: str,
    ) -> ToolRequest | None:
        """
        Route either a website or an installed application.

        Known websites are handled before applications.

        Obvious file and folder targets are rejected before
        generic domain detection so names such as notes.txt
        cannot be mistaken for websites.
        """

        match = (
            self._OPEN_TARGET_PATTERN.fullmatch(
                prompt
            )
        )

        if match is None:
            return None

        target = match.group(
            1
        ).strip()

        if not target:
            return None

        lowered_target = (
            target.casefold()
        )

        # =================================================
        # COMPLEX / MULTI-STEP REQUEST
        # =================================================

        if any(
            word in f" {lowered_target} "
            for word in self._CHAIN_WORDS
        ):
            return None

        if len(target) > 2048:
            return None

        # =================================================
        # FRIENDLY "THE" PREFIX
        # =================================================

        if lowered_target.startswith(
            "the "
        ):
            target = target[
                4:
            ].strip()

            lowered_target = (
                target.casefold()
            )

        if not target:
            return None

        # =================================================
        # KNOWN WEBSITE ALIASES
        # =================================================

        known_url = (
            self._WEBSITE_ALIASES.get(
                lowered_target
            )
        )

        if known_url is not None:
            return ToolRequest(
                tool_name="open_url",
                arguments={
                    "url": known_url,
                },
            )

        # =================================================
        # FILESYSTEM TARGET
        # =================================================
        #
        # IMPORTANT:
        #
        # This check must happen BEFORE generic domain
        # recognition.
        #
        # Otherwise:
        #
        #     notes.txt
        #
        # could incorrectly become:
        #
        #     https://notes.txt
        # =================================================

        if self._looks_like_filesystem_target(
            lowered_target
        ):
            return None

        # =================================================
        # EXPLICIT / DOMAIN URL
        # =================================================

        explicit_url = (
            self._normalize_explicit_url(
                target
            )
        )

        if explicit_url is not None:
            return ToolRequest(
                tool_name="open_url",
                arguments={
                    "url": explicit_url,
                },
            )

        # =================================================
        # INSTALLED APPLICATION
        # =================================================

        if len(target) > 100:
            return None

        return ToolRequest(
            tool_name="open_application",
            arguments={
                "application": target,
            },
        )

    @staticmethod
    def _normalize_explicit_url(
        target: str,
    ) -> str | None:
        """
        Recognize explicit safe web addresses.

        Supported:

            https://example.com
            http://example.com
            example.com
            www.example.com

        OpenUrlTool performs the final security validation.
        """

        lowered = (
            target.casefold()
        )

        if lowered.startswith(
            (
                "https://",
                "http://",
            )
        ):
            parsed = urlsplit(
                target
            )

            if parsed.hostname:
                return target

            return None

        if " " in target:
            return None

        if "." not in target:
            return None

        candidate = (
            f"https://{target}"
        )

        parsed = urlsplit(
            candidate
        )

        hostname = parsed.hostname

        if (
            hostname is None
            or "." not in hostname
        ):
            return None

        return candidate

    @staticmethod
    def _looks_like_filesystem_target(
        target: str,
    ) -> bool:
        """
        Detect obvious file/folder targets.

        Common file extensions are treated as filesystem targets
        while normal domains such as example.com remain eligible
        for URL routing.
        """

        if "\\" in target:
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

        return bool(
            re.search(
                (
                    r"\.(?:"
                    r"txt|pdf|doc|docx|xls|xlsx|csv|"
                    r"json|py|md|zip|rar|7z|exe|msi"
                    r")$"
                ),
                target,
                re.IGNORECASE,
            )
        )
