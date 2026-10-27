from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from jarvis.runtime.profile import (
    AgentEngineId,
    RuntimeMode,
    RuntimeProfile,
)


class RouteTarget(StrEnum):
    """
    Execution target selected after the deterministic fast path
    has declined a request.
    """

    NATIVE = "native"
    HERMES = "hermes"
    OPENAI = "openai"


@dataclass(
    frozen=True,
    slots=True,
)
class RouteDecision:
    """
    One explainable routing decision.

    use_cloud matters only when the selected target is Hermes.

    use_tools distinguishes normal cloud reasoning from requests
    that need the trusted JARVIS MCP action bridge.
    """

    target: RouteTarget
    reason: str
    complexity_score: int
    use_cloud: bool = False
    use_tools: bool = False


class RequestRouter:
    """
    Lightweight policy router for JARVIS AI requests.

    This router runs only AFTER FastCommandRouter has declined
    the prompt.

    It does not execute tools, call models, grant permissions,
    access credentials, or perform network requests.

    Product policy:

        Explicit Native
            -> Native

        Explicit Hermes
            -> Hermes
            -> local/cloud follows RuntimeMode

        AUTO + LOCAL
            -> Native for ordinary work
            -> local Hermes for sufficiently complex work

        AUTO + AUTO
            -> local-first
            -> Native for ordinary work
            -> local Hermes for sufficiently complex work

        AUTO + SMART
            -> cloud Hermes for normal reasoning
            -> cloud Hermes + trusted JARVIS bridge for
               Windows/UI action requests
            -> Native for local filesystem actions until a
               trusted cloud filesystem bridge exists

        AUTO + MAXIMUM
            -> strongest cloud Hermes path
            -> same trusted-tool boundary as SMART

    Fast deterministic commands are handled before this router,
    so simple commands such as opening a known application or
    website still avoid an AI model completely.
    """

    _MULTI_STEP_PATTERNS = (
        " and then ",
        " then ",
        " after that ",
        " once that ",
        " when you finish ",
        " step by step ",
        " first ",
        " finally ",
    )

    _COMPLEX_TASK_TERMS = frozenset(
        {
            "analyse",
            "analyze",
            "architecture",
            "architect",
            "benchmark",
            "build",
            "code",
            "compare",
            "debug",
            "design",
            "develop",
            "diagnose",
            "evaluate",
            "fix",
            "implement",
            "investigate",
            "optimize",
            "optimise",
            "plan",
            "program",
            "refactor",
            "research",
            "review",
            "rewrite",
            "strategy",
            "test",
            "troubleshoot",
        }
    )

    _AGENTIC_TASK_TERMS = frozenset(
        {
            "browser",
            "browse",
            "download",
            "email",
            "find",
            "install",
            "navigate",
            "search",
            "website",
        }
    )

    _HIGH_COMPLEXITY_TERMS = frozenset(
        {
            "deep research",
            "deeply analyze",
            "deeply analyse",
            "full research",
            "multi-agent",
            "multiple agents",
            "complete implementation",
            "end to end",
            "end-to-end",
        }
    )

    _TRUSTED_WINDOWS_ACTION_TERMS = frozenset(
        {
            "open",
            "launch",
            "close",
            "click",
            "type",
            "press",
            "minimize",
            "minimise",
            "maximize",
            "maximise",
            "restore",
            "focus",
        }
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
        "can you explain ",
        "could you explain ",
    )

    _LOCAL_FILE_ACTION_PATTERNS = (
        "read file",
        "read the file",
        "write file",
        "write to file",
        "write to the file",
        "delete file",
        "delete the file",
        "trash file",
        "trash the file",
        "open file",
        "open the file",
        "open folder",
        "open the folder",
        "list files",
        "list the files",
        "list directory",
        "list the directory",
    )

    _FILE_EXTENSION_PATTERN = re.compile(
        r"\.(?:txt|pdf|doc|docx|xls|xlsx|csv|json|py|md|yaml|yml)$",
        re.IGNORECASE,
    )

    _WORD_PATTERN = re.compile(
        r"[a-zA-Z0-9_-]+"
    )

    def route(
        self,
        prompt: str,
        profile: RuntimeProfile,
        direct_cloud_available: bool = False,
    ) -> RouteDecision:
        """
        Decide which AI runtime should handle one prompt.
        """

        normalized = self._normalize(
            prompt
        )

        complexity_score = (
            self._complexity_score(
                normalized
            )
        )

        configured_engine = (
            profile.agent_engine
        )

        mode = profile.mode

        needs_tools = (
            self._requires_trusted_windows_tools(
                normalized
            )
        )

        # =================================================
        # EXPLICIT ENGINE OVERRIDES
        # =================================================

        if (
            configured_engine
            is AgentEngineId.NATIVE
        ):
            return RouteDecision(
                target=RouteTarget.NATIVE,
                reason=(
                    "Native JARVIS was explicitly selected."
                ),
                complexity_score=complexity_score,
            )

        if (
            configured_engine
            is AgentEngineId.HERMES
        ):
            use_cloud = (
                mode
                in {
                    RuntimeMode.SMART,
                    RuntimeMode.MAXIMUM,
                }
            )

            location = (
                "cloud"
                if use_cloud
                else "local"
            )

            return RouteDecision(
                target=RouteTarget.HERMES,
                reason=(
                    "Hermes was explicitly selected; "
                    f"{mode.value} mode chooses the "
                    f"{location} Hermes runtime."
                ),
                complexity_score=complexity_score,
                use_cloud=use_cloud,
                use_tools=needs_tools,
            )

        # =================================================
        # AUTO ENGINE: LOCAL FILE ACTION SAFETY
        # =================================================
        #
        # The current cloud Hermes bridge intentionally does
        # not expose arbitrary filesystem access. Keep those
        # requests on Native until the trusted cloud filesystem
        # bridge is implemented.
        # =================================================

        if (
            mode
            in {
                RuntimeMode.SMART,
                RuntimeMode.MAXIMUM,
            }
            and self._requires_local_file_runtime(
                normalized
            )
        ):
            return RouteDecision(
                target=RouteTarget.NATIVE,
                reason=(
                    "This request needs local filesystem tools, "
                    "which remain on the trusted Native runtime."
                ),
                complexity_score=complexity_score,
            )

        # =================================================
        # Direct API avoids starting Hermes for ordinary reasoning.
        if direct_cloud_available and mode is not RuntimeMode.LOCAL:
            if needs_tools:
                return RouteDecision(
                    target=RouteTarget.HERMES,
                    reason="This action needs the trusted Hermes bridge.",
                    complexity_score=complexity_score,
                    use_cloud=True,
                    use_tools=True,
                )
            return RouteDecision(
                target=RouteTarget.OPENAI,
                reason="Direct OpenAI reasoning avoids Hermes process startup.",
                complexity_score=complexity_score,
                use_cloud=True,
            )

        # MAXIMUM
        # =================================================

        if mode is RuntimeMode.MAXIMUM:
            return RouteDecision(
                target=RouteTarget.HERMES,
                reason=(
                    "Maximum mode selected the strongest cloud "
                    "Hermes runtime."
                ),
                complexity_score=complexity_score,
                use_cloud=True,
                use_tools=needs_tools,
            )

        # =================================================
        # SMART
        # =================================================
        #
        # This is the important product change:
        #
        # Smart no longer sends ordinary reasoning to the small
        # local model. The deterministic fast path already handles
        # cheap commands, so remaining normal reasoning should use
        # the stronger cloud runtime.
        # =================================================

        if mode is RuntimeMode.SMART:
            if needs_tools:
                reason = (
                    "Smart mode selected cloud Hermes with the "
                    "trusted JARVIS action bridge."
                )

            elif complexity_score >= 2:
                reason = (
                    "Smart mode selected cloud Hermes for a "
                    "complex reasoning request."
                )

            else:
                reason = (
                    "Smart mode selected cloud Hermes instead "
                    "of the lightweight local model."
                )

            return RouteDecision(
                target=RouteTarget.HERMES,
                reason=reason,
                complexity_score=complexity_score,
                use_cloud=True,
                use_tools=needs_tools,
            )

        # =================================================
        # LOCAL
        # =================================================

        if mode is RuntimeMode.LOCAL:
            if complexity_score >= 3:
                return RouteDecision(
                    target=RouteTarget.HERMES,
                    reason=(
                        "Local mode selected local Hermes "
                        "for a complex request without "
                        "allowing cloud execution."
                    ),
                    complexity_score=complexity_score,
                    use_cloud=False,
                    use_tools=True,
                )

            return RouteDecision(
                target=RouteTarget.NATIVE,
                reason=(
                    "Local mode selected the lightweight "
                    "Native runtime."
                ),
                complexity_score=complexity_score,
            )

        # =================================================
        # AUTO
        # =================================================
        #
        # AUTO remains privacy-first/local-first.
        # It does not silently send prompts to cloud.
        # =================================================

        if complexity_score >= 3:
            return RouteDecision(
                target=RouteTarget.HERMES,
                reason=(
                    "Auto mode selected local Hermes because "
                    "the request appears complex."
                ),
                complexity_score=complexity_score,
                use_cloud=False,
                use_tools=True,
            )

        return RouteDecision(
            target=RouteTarget.NATIVE,
            reason=(
                "Auto mode selected the faster local Native "
                "runtime for an ordinary request."
            ),
            complexity_score=complexity_score,
        )

    def _complexity_score(
        self,
        prompt: str,
    ) -> int:
        """
        Produce a small deterministic complexity score.

        The score is only a routing hint. It is not a general
        measurement of intelligence or task difficulty.
        """

        if not prompt:
            return 0

        lowered = prompt.casefold()

        words = {
            word.casefold()
            for word in self._WORD_PATTERN.findall(
                lowered
            )
        }

        score = 0

        if words.intersection(
            self._COMPLEX_TASK_TERMS
        ):
            score += 1

        if words.intersection(
            self._AGENTIC_TASK_TERMS
        ):
            score += 1

        if any(
            pattern in f" {lowered} "
            for pattern
            in self._MULTI_STEP_PATTERNS
        ):
            score += 1

        if any(
            phrase in lowered
            for phrase
            in self._HIGH_COMPLEXITY_TERMS
        ):
            score += 2

        word_count = len(
            self._WORD_PATTERN.findall(
                prompt
            )
        )

        if word_count >= 45:
            score += 1

        if word_count >= 100:
            score += 1

        return score

    def _requires_trusted_windows_tools(
        self,
        prompt: str,
    ) -> bool:
        """
        Detect direct Windows/UI action intent.

        Informational questions stay on the no-bridge cloud path.
        """

        lowered = prompt.casefold().strip()

        if not lowered:
            return False

        if lowered.startswith(
            self._INFORMATIONAL_PREFIXES
        ):
            return False

        words = {
            word.casefold()
            for word in self._WORD_PATTERN.findall(
                lowered
            )
        }

        return bool(
            words.intersection(
                self._TRUSTED_WINDOWS_ACTION_TERMS
            )
        )

    def _requires_local_file_runtime(
        self,
        prompt: str,
    ) -> bool:
        """
        Keep direct filesystem actions on Native for now.

        This avoids pretending the current cloud Hermes bridge
        has file authority that it intentionally does not have.
        """

        lowered = prompt.casefold().strip()

        if not lowered:
            return False

        if lowered.startswith(
            self._INFORMATIONAL_PREFIXES
        ):
            return False

        if "\\" in prompt:
            return True

        if any(
            pattern in lowered
            for pattern
            in self._LOCAL_FILE_ACTION_PATTERNS
        ):
            return True

        return bool(
            self._FILE_EXTENSION_PATTERN.search(
                lowered
            )
        )

    @staticmethod
    def _normalize(
        prompt: str,
    ) -> str:
        return " ".join(
            prompt
            .strip()
            .split()
        )
