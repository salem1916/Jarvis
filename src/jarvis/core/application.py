import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from jarvis.agents.base import AgentEngine
from jarvis.agents.hermes import HermesAgentEngine
from jarvis.agents.native import NativeAgentEngine
from jarvis.agents.team import AgentTeam, WorkerDefinition
from jarvis.core.action_confirmation import (
    ActionConfirmationHandler,
    ActionConfirmationRequest,
    ActionDeclinedError,
)
from jarvis.core.action_memory import (
    ActionMemory,
    ActionMemoryEntry,
)
from jarvis.core.agent_service import AgentService
from jarvis.core.assistant_commands import assistant_command
from jarvis.core.conversation import Conversation
from jarvis.core.fast_command_router import FastCommandRouter
from jarvis.core.personal_memory import PersonalMemory
from jarvis.core.request_router import (
    RequestRouter,
    RouteDecision,
    RouteTarget,
)
from jarvis.core.tool_request import ToolRequest
from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
)
from jarvis.models.catalog import (
    ModelDefinition,
    ProviderDefinition,
)
from jarvis.runtime.model_manager import ModelManager
from jarvis.runtime.profile import (
    AgentEngineId,
    ModelRole,
    ModelSelection,
    RuntimeMode,
    RuntimeProfile,
)
from jarvis.security.capabilities import Capability
from jarvis.security.filesystem_scope import FilesystemScopePolicy
from jarvis.security.filesystem_scope_store import FilesystemScopeStore
from jarvis.security.permission_mode import PermissionMode
from jarvis.security.permission_mode_store import PermissionModeStore
from jarvis.security.policy import PermissionDecision
from jarvis.tools.executor import ConfirmationRequiredError
from jarvis.tools.service import ToolService


@dataclass(
    frozen=True,
    slots=True,
)
class ExecutionTelemetry:
    """
    Human-readable summary of the latest JARVIS execution.

    This intentionally records routing/runtime metadata only.
    It does not store the user's prompt, model response, tool
    arguments, credentials, or file contents.
    """

    route: str
    engine: str
    duration_seconds: float
    tool_name: str | None = None
    model: str | None = None
    reason: str | None = None

    def summary(
        self,
    ) -> str:
        parts = [
            f"Route: {self.route}",
            f"Engine: {self.engine}",
        ]

        if self.model:
            parts.append(
                f"Model: {self.model}"
            )

        if self.tool_name:
            parts.append(
                f"Tool: {self.tool_name}"
            )

        parts.append(
            f"Latency: {self.duration_seconds:.1f}s"
        )

        return " | ".join(
            parts
        )


@dataclass(
    frozen=True,
    slots=True,
)
class TimedOpenCloseCommand:
    open_request: ToolRequest
    seconds: int
    close_target: str


@dataclass(
    frozen=True,
    slots=True,
)
class FastWriteFileCommand:
    request: ToolRequest
    target_label: str


_MAX_TIMED_OPEN_CLOSE_SECONDS = 60

_DEFAULT_FAST_NOTE_FILENAME = "jarvis-note.txt"

_FAST_WRITE_LOCATION_ALIASES = {
    "desktop": "Desktop",
    "documents": "Documents",
    "document": "Documents",
    "downloads": "Downloads",
    "download": "Downloads",
    "workspace": "",
    "jarvis": "",
}

_FAST_WRITE_FILE_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".csv",
}

_GENERATIVE_FILE_CONTENT_TERMS = {
    "article",
    "brief",
    "description",
    "draft",
    "email",
    "essay",
    "explanation",
    "guide",
    "instructions",
    "letter",
    "message",
    "plan",
    "poem",
    "recipe",
    "report",
    "steps",
    "story",
    "summary",
}

_FAST_WRITE_FILENAME_STOPWORDS = {
    "a",
    "an",
    "and",
    "about",
    "add",
    "for",
    "how",
    "make",
    "me",
    "of",
    "on",
    "put",
    "the",
    "to",
    "write",
}

_CLOSE_LAST_OPENED_COMMANDS = {
    "close the last thing you opened",
    "close last thing you opened",
    "close what you opened",
    "close the last opened thing",
    "close last opened thing",
    "close last opened",
}

_LIST_OPEN_ACTIONS_COMMANDS = {
    "what did you open",
    "what have you opened",
    "what is open",
    "what did jarvis open",
    "show what you opened",
    "list what you opened",
    "list opened things",
}

_ASSISTANT_STATUS_COMMANDS = {
    "jarvis status",
    "status report",
    "system status",
    "assistant status",
}

_ASSISTANT_BRIEFING_COMMANDS = {
    "daily brief",
    "daily briefing",
    "morning brief",
    "morning briefing",
    "brief me",
    "what is my briefing",
}

_ASSISTANT_CAPABILITY_COMMANDS = {
    "what can you do",
    "what can jarvis do",
    "help",
    "jarvis help",
    "show capabilities",
}

_ASSISTANT_PLAN_COMMANDS = {
    "assistant plan",
    "jarvis plan",
    "product plan",
    "roadmap",
    "what are we building",
}

_ASSISTANT_COMMAND_CENTER_COMMANDS = {
    "command center",
    "jarvis command center",
    "mission control",
    "what now",
    "what should we do now",
    "next real step",
}

_CLOSE_REMEMBERED_ACTION_PATTERN = re.compile(
    r"^(?:please\s+)?"
    r"close\s+"
    r"(?P<target>.+?)"
    r"(?:\s+please)?[.!]?$",
    re.IGNORECASE,
)

_TIMED_OPEN_CLOSE_PATTERNS: tuple[
    re.Pattern[str],
    ...,
] = (
    re.compile(
        r"^(?:please\s+)?"
        r"(?P<action>open|launch|visit|browse(?:\s+to)?|go\s+to)\s+"
        r"(?P<target>.+?)\s+"
        r"(?:and\s+)?(?:then\s+)?wait\s+"
        r"(?:for\s+)?(?:about\s+)?"
        r"(?P<seconds>[1-9]\d?)\s*"
        r"(?:seconds?|secs?|s)\s+"
        r"(?:and\s+)?(?:then\s+)?close\s+"
        r"(?:it|the\s+(?:window|browser|tab|app|application))"
        r"(?:\s+please)?[.!]?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:please\s+)?"
        r"(?P<action>open|launch|visit|browse(?:\s+to)?|go\s+to)\s+"
        r"(?P<target>.+?)\s+"
        r"(?:and\s+)?(?:then\s+)?close\s+"
        r"(?:it|the\s+(?:window|browser|tab|app|application))\s+"
        r"after\s+(?:about\s+)?"
        r"(?P<seconds>[1-9]\d?)\s*"
        r"(?:seconds?|secs?|s)"
        r"(?:\s+please)?[.!]?$",
        re.IGNORECASE,
    ),
)

_FAST_WRITE_FILENAME_PATTERN = re.compile(
    r"\b(?:called|named|as)\s+"
    r"(?P<filename>[\w ._-]+?"
    r"(?:\.(?:txt|md|json|csv))?)"
    r"(?=\s+(?:and|with|that|saying|containing)\b|$)",
    re.IGNORECASE,
)

_FAST_WRITE_CONTENT_PATTERNS: tuple[
    re.Pattern[str],
    ...,
] = (
    re.compile(
        r"\b(?:say|write|put)\s+"
        r"(?P<content>.+?)\s+"
        r"(?:in there|inside it|in it|into it|to it)"
        r"(?:\s+please)?[.!]?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:that\s+says|saying|with\s+content|containing)\s+"
        r"(?P<content>.+?)"
        r"(?:\s+please)?[.!]?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:please\s+)?(?:ok(?:ay)?\s+)?"
        r"(?:write|put)\s+"
        r"(?P<content>.+?)\s+"
        r"(?:to|into|in)\s+"
        r"(?:a\s+|the\s+)?(?:new\s+)?(?:text\s+)?file\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\band\s+(?:put|write|add)\s+"
        r"(?P<content>.+?)"
        r"(?:\s+please)?[.!]?$",
        re.IGNORECASE,
    ),
)


class JarvisApplication:
    """
    Main trusted application facade for JARVIS.

    Runtime routing:

        request
            |
            v
        FastCommandRouter
            |
            +-- recognized
            |       |
            |       v
            |   trusted ToolService
            |
            +-- not recognized
                    |
                    v
              RequestRouter
                 /     \\
                v       v
             Native   Hermes
                |       |
                v       v
             model    local/cloud

        SMART ordinary reasoning
            -> cloud Hermes without JARVIS MCP bridge

        SMART trusted Windows/UI action
            -> cloud Hermes with JARVIS MCP bridge

    The routing layer decides which already-trusted runtime
    receives an AI request.

    It never grants permissions and never bypasses ToolService.
    """

    def __init__(
        self,
        tool_service: ToolService,
        model_provider: ModelProvider,
        filesystem_scope_policy: FilesystemScopePolicy | None = None,
        filesystem_scope_store: FilesystemScopeStore | None = None,
        permission_mode_store: PermissionModeStore | None = None,
        permission_modes: dict[
            Capability,
            PermissionMode,
        ] | None = None,
        model_manager: ModelManager | None = None,
        fast_command_router: FastCommandRouter | None = None,
        request_router: RequestRouter | None = None,
        hermes_agent_engine: AgentEngine | None = None,
        action_memory: ActionMemory | None = None,
        personal_memory: PersonalMemory | None = None,
        cloud_provider: ModelProvider | None = None,
        local_worker_provider: ModelProvider | None = None,
        prefer_cloud_reasoning: bool = True,
    ) -> None:
        self.tool_service = tool_service

        self.model_provider = model_provider
        self.model_manager = model_manager
        self.personal_memory = personal_memory if personal_memory is not None else PersonalMemory()
        self.cloud_provider = cloud_provider
        self.local_worker_provider = local_worker_provider or model_provider
        self.prefer_cloud_reasoning = prefer_cloud_reasoning
        self.agent_team = AgentTeam(self.personal_memory, self._run_independent_worker)

        self.filesystem_scope_policy = filesystem_scope_policy
        self.filesystem_scope_store = filesystem_scope_store

        self.permission_mode_store = permission_mode_store

        self._permission_modes = dict(
            permission_modes or {}
        )

        self._persistent_permission_modes = {
            capability: mode
            for capability, mode
            in self._permission_modes.items()
            if mode is not PermissionMode.ALLOW_SESSION
        }

        # =================================================
        # ROUTERS
        # =================================================

        self.fast_command_router = (
            fast_command_router
            if fast_command_router is not None
            else FastCommandRouter()
        )

        self.request_router = (
            request_router
            if request_router is not None
            else RequestRouter()
        )

        self._last_route_decision: (
            RouteDecision
            | None
        ) = None

        self._last_execution_telemetry: (
            ExecutionTelemetry
            | None
        ) = None

        self.action_memory = (
            action_memory
            if action_memory is not None
            else ActionMemory()
        )

        # =================================================
        # NATIVE AGENT
        # =================================================

        self.agent_service = (
            self._build_agent_service(
                model_provider
            )
        )

        self.native_agent_engine = (
            NativeAgentEngine(
                self.agent_service
            )
        )

        # =================================================
        # HERMES AGENTS
        # =================================================

        # Tests and custom integrations may inject one Hermes
        # engine. When supplied, use it for every Hermes path.
        if hermes_agent_engine is not None:
            self.hermes_cloud_chat_agent_engine = (
                hermes_agent_engine
            )

            self.hermes_cloud_agent_engine = (
                hermes_agent_engine
            )

            self.hermes_local_agent_engine = (
                hermes_agent_engine
            )

        else:
            # Fast cloud reasoning path:
            #
            # No JARVIS ToolService is attached, so Hermes does
            # not start the MCP bridge for ordinary chat/reasoning.
            # This still uses the user's existing Hermes/Codex
            # cloud configuration.
            gateway_api_key = os.getenv(
                "JARVIS_HERMES_GATEWAY_KEY"
            )

            gateway_url = os.getenv(
                "JARVIS_HERMES_GATEWAY_URL",
                "http://127.0.0.1:8642",
            )

            self.hermes_cloud_chat_agent_engine = (
                HermesAgentEngine(
                    tool_service=None,
                    gateway_url=(
                        gateway_url
                        if gateway_api_key
                        else None
                    ),
                    gateway_api_key=(
                        gateway_api_key
                    ),
                    gateway_model="hermes-agent",
                )
            )

            # Cloud action path:
            #
            # Only requests that actually need trusted Windows/UI
            # actions pay the cost of starting the JARVIS bridge.
            self.hermes_cloud_agent_engine = (
                HermesAgentEngine(
                    tool_service=self.tool_service,
                )
            )

            self.hermes_local_agent_engine = (
                self._build_local_hermes_engine()
            )

        # Compatibility alias for code that still expects one
        # Hermes engine.
        self.hermes_agent_engine = (
            self.hermes_cloud_agent_engine
        )

        # This remains useful for compatibility and for showing
        # the most recently selected runtime.
        self.agent_engine: AgentEngine = (
            self.native_agent_engine
        )

        self.conversation = Conversation()

        self._activate_agent_engine(
            self._configured_agent_engine()
        )

    # =================================================
    # AGENT CONSTRUCTION
    # =================================================

    def _build_agent_service(
        self,
        model_provider: ModelProvider,
    ) -> AgentService:
        return AgentService(
            model_provider=model_provider,
            tool_service=self.tool_service,
        )

    def _configured_agent_engine(
        self,
    ) -> AgentEngineId:
        if self.model_manager is None:
            return AgentEngineId.NATIVE

        return (
            self.model_manager
            .profile()
            .agent_engine
        )

    def _local_hermes_model_id(
        self,
    ) -> str:
        """
        Hermes Local follows the configured MAIN Ollama model.

        If model management is unavailable, use the known
        lightweight fallback.
        """

        if self.model_manager is not None:
            selection = (
                self.model_manager
                .profile()
                .model_for(
                    ModelRole.MAIN
                )
            )

            if (
                selection is not None
                and selection.provider_id
                == "ollama"
            ):
                return selection.model_id

        if self.local_worker_provider.name == "ollama":
            model = getattr(self.local_worker_provider, "model", None)
            if isinstance(model, str):
                return model
        return "qwen3.5:4b"

    def _ollama_openai_base_url(
        self,
    ) -> str:
        """
        Determine the OpenAI-compatible Ollama endpoint.

        Prefer the active provider's configured URL when
        available, otherwise use the standard local endpoint.
        """

        raw_base_url = getattr(
            self.local_worker_provider,
            "base_url",
            "http://127.0.0.1:11434",
        )

        if not isinstance(
            raw_base_url,
            str,
        ):
            raw_base_url = (
                "http://127.0.0.1:11434"
            )

        base_url = (
            raw_base_url.rstrip("/")
        )

        if base_url.endswith(
            "/v1"
        ):
            return base_url

        return (
            f"{base_url}/v1"
        )

    def _build_local_hermes_engine(
        self,
    ) -> HermesAgentEngine:
        """
        Build a completely local Hermes runtime.

        The API key is a dummy local value required by the
        OpenAI-compatible client. It is not a cloud credential.
        """

        return HermesAgentEngine(
            tool_service=self.tool_service,
            provider="openai-api",
            model=self._local_hermes_model_id(),
            base_url=self._ollama_openai_base_url(),
            api_key="local",
        )

    def _rebuild_local_hermes_engine(
        self,
    ) -> None:
        """
        Rebuild Hermes Local after changing the MAIN model.
        """

        self.hermes_local_agent_engine = (
            self._build_local_hermes_engine()
        )

    # =================================================
    # RUNTIME PROFILE / ROUTING
    # =================================================

    def _active_runtime_mode(
        self,
    ) -> RuntimeMode:
        if self.model_manager is None:
            return RuntimeMode.AUTO

        return (
            self.model_manager
            .profile()
            .mode
        )

    def _routing_profile(
        self,
    ) -> RuntimeProfile:
        """
        Return the policy state used for one routing decision.

        Applications without ModelManager preserve the legacy
        Native behavior.
        """

        if self.model_manager is None:
            return RuntimeProfile(
                mode=RuntimeMode.AUTO,
                agent_engine=AgentEngineId.NATIVE,
            )

        return (
            self.model_manager
            .profile()
        )

    def _activate_agent_engine(
        self,
        agent_engine: AgentEngineId,
    ) -> None:
        """
        Activate the statically configured runtime.

        RequestRouter may temporarily choose another engine for
        individual requests when AgentEngineId.AUTO is selected.
        """

        if agent_engine is not AgentEngineId.HERMES:
            self.agent_engine = (
                self.native_agent_engine
            )

            return

        mode = self._active_runtime_mode()

        if mode in {
            RuntimeMode.SMART,
            RuntimeMode.MAXIMUM,
        }:
            selected_engine = (
                self.hermes_cloud_agent_engine
            )

        else:
            selected_engine = (
                self.hermes_local_agent_engine
            )

        self._ensure_engine_available(
            selected_engine
        )

        self.agent_engine = (
            selected_engine
        )

    @staticmethod
    def _ensure_engine_available(
        engine: AgentEngine,
    ) -> None:
        """
        Validate a real Hermes installation when applicable.

        Injected test/custom AgentEngine implementations are
        already considered available.
        """

        if (
            isinstance(
                engine,
                HermesAgentEngine,
            )
            and not engine.is_available()
        ):
            raise RuntimeError(
                "Hermes Agent is not installed "
                "or is not available on PATH."
            )

    def _engine_for_route(
        self,
        decision: RouteDecision,
    ) -> AgentEngine:
        """
        Resolve a RequestRouter decision into a concrete
        already-configured agent runtime.
        """

        if decision.target is RouteTarget.OPENAI:
            if self.cloud_provider is None:
                raise ValueError("OpenAI is not configured. Set JARVIS_OPENAI_API_KEY locally and restart JARVIS.")
            return NativeAgentEngine(self._build_agent_service(self.cloud_provider))

        if (
            decision.target
            is RouteTarget.NATIVE
        ):
            if self._active_runtime_mode() is RuntimeMode.LOCAL or decision.reason == "Explicit @local request.":
                return NativeAgentEngine(self._build_agent_service(self.local_worker_provider))
            return (
                self.native_agent_engine
            )

        if decision.use_cloud:
            if decision.use_tools:
                engine = (
                    self.hermes_cloud_agent_engine
                )

            else:
                engine = (
                    self.hermes_cloud_chat_agent_engine
                )

        else:
            engine = (
                self.hermes_local_agent_engine
            )

        self._ensure_engine_available(
            engine
        )

        return engine

    def _route_agent_request(
        self,
        prompt: str,
        agent_override: str | None = None,
    ) -> AgentEngine:
        """
        Route one non-fast request to Native or Hermes.

        This method performs no inference itself.
        """

        if agent_override:
            local_mode = self._active_runtime_mode() is RuntimeMode.LOCAL
            if local_mode and agent_override in {"chatgpt", "hermes"}:
                raise ValueError("Local mode blocks cloud agents. Change the mode in Models first.")
            decision = RouteDecision(
                target={"chatgpt": RouteTarget.OPENAI, "hermes": RouteTarget.HERMES,
                        "local": RouteTarget.NATIVE}[agent_override],
                reason=f"Explicit @{agent_override} request.", complexity_score=0,
                use_cloud=agent_override != "local",
                use_tools=agent_override == "hermes",
            )
        elif self.cloud_provider is not None and self.prefer_cloud_reasoning:
            decision = self.request_router.route(
                prompt, self._routing_profile(), direct_cloud_available=True)
        else:
            decision = self.request_router.route(prompt, self._routing_profile())

        engine = (
            self._engine_for_route(
                decision
            )
        )

        self._last_route_decision = (
            decision
        )

        # Keep the compatibility field aligned with the runtime
        # actually selected for the latest request.
        self.agent_engine = engine

        return engine

    def last_route_decision(
        self,
    ) -> RouteDecision | None:
        """
        Return the most recent AI routing decision.

        Fast deterministic commands do not have one.
        """

        return self._last_route_decision

    def last_execution_telemetry(
        self,
    ) -> ExecutionTelemetry | None:
        """
        Return the latest runtime/latency summary.

        This is safe for UI display because it contains only
        route names, engine/model labels, tool names, timing,
        and router reasons.
        """

        return self._last_execution_telemetry

    # =================================================
    # TRUSTED TOOL EXECUTION
    # =================================================

    def execute_tool(
        self,
        request: ToolRequest,
        *,
        confirmed: bool = False,
    ) -> object:
        return self.tool_service.execute(
            request,
            confirmed=confirmed,
        )

    def _execute_tool_with_confirmation(
        self,
        request: ToolRequest,
        confirmation_handler: (
            ActionConfirmationHandler
            | None
        ),
    ) -> object:
        try:
            return self.tool_service.execute(
                request
            )

        except ConfirmationRequiredError:
            if confirmation_handler is None:
                raise

            tool = (
                self.tool_service
                .registry
                .get(
                    request.tool_name
                )
            )

            confirmation = (
                ActionConfirmationRequest(
                    tool_name=request.tool_name,
                    capability=tool.required_capability,
                    arguments=dict(
                        request.arguments
                    ),
                )
            )

            approved = (
                confirmation_handler
                .confirm(
                    confirmation
                )
            )

            if not approved:
                raise ActionDeclinedError(
                    "The user declined the requested action."
                )

            return self.tool_service.execute(
                request,
                confirmed=True,
            )

    # =================================================
    # FAST COMMAND PATH
    # =================================================

    def _try_fast_command(
        self,
        prompt: str,
        confirmation_handler: (
            ActionConfirmationHandler
            | None
        ),
    ) -> tuple[
        str,
        ToolRequest,
    ] | None:
        request = (
            self.fast_command_router
            .route(
                prompt
            )
        )

        if request is None:
            return None

        try:
            result = (
                self._execute_tool_with_confirmation(
                    request=request,
                    confirmation_handler=(
                        confirmation_handler
                    ),
                )
            )

        except (
            KeyError,
            ValueError,
        ):
            return None

        self._remember_open_action(
            request
        )

        return (
            self._format_fast_command_result(
                request=request,
                result=result,
            ),
            request,
        )

    def _try_timed_open_close_command(
        self,
        prompt: str,
        confirmation_handler: (
            ActionConfirmationHandler
            | None
        ),
    ) -> tuple[
        str,
        str,
    ] | None:
        command = (
            self._parse_timed_open_close_command(
                prompt
            )
        )

        if command is None:
            return None

        try:
            self.tool_service.registry.get(
                command.open_request.tool_name
            )

            close_request = (
                self._close_request_for_timed_open_close(
                    command
                )
            )

            self.tool_service.registry.get(
                close_request.tool_name
            )

        except KeyError:
            return (
                (
                    "I remembered the action, but the "
                    "required close tool is not available."
                ),
                "action_memory",
            )

        try:
            self._execute_tool_with_confirmation(
                request=command.open_request,
                confirmation_handler=(
                    confirmation_handler
                ),
            )

        except (
            KeyError,
            ValueError,
        ):
            return None

        memory_entry = (
            self._remember_open_action(
                command.open_request
            )
        )

        time.sleep(
            command.seconds
        )

        try:
            close_result = (
                self._execute_tool_with_confirmation(
                    request=close_request,
                    confirmation_handler=(
                        confirmation_handler
                    ),
                )
            )

            if memory_entry is not None:
                self.action_memory.mark_closed(
                    memory_entry.entry_id,
                    closed_at=time.time(),
                )

        except ValueError as exc:
            return (
                self._format_timed_open_close_failure(
                    command=command,
                    error=exc,
                ),
                (
                    f"{command.open_request.tool_name} "
                    f"+ wait + {close_request.tool_name}"
                ),
            )

        return (
            self._format_timed_open_close_result(
                command=command,
                close_result=close_result,
            ),
            (
                f"{command.open_request.tool_name} "
                f"+ wait + {close_request.tool_name}"
            ),
        )

    def _try_memory_close_command(
        self,
        prompt: str,
        confirmation_handler: (
            ActionConfirmationHandler
            | None
        ),
    ) -> tuple[
        str,
        str,
    ] | None:
        normalized = " ".join(
            prompt
            .strip()
            .casefold()
            .split()
        )

        list_result = (
            self._try_memory_list_command(
                normalized
            )
        )

        if list_result is not None:
            return list_result

        if (
            normalized
            in _CLOSE_LAST_OPENED_COMMANDS
        ):
            entry = (
                self.action_memory
                .last_open_entry()
            )

            return self._close_memory_entry(
                entry=entry,
                confirmation_handler=(
                    confirmation_handler
                ),
                response_prefix=(
                    "Closed the last thing I opened"
                ),
            )

        close_target = (
            self._memory_close_target_from_prompt(
                prompt
            )
        )

        if close_target is None:
            return None

        named_entry = (
            self.action_memory
            .find_open_entry(
                close_target
            )
        )

        if named_entry is None:
            return (
                (
                    "I do not have a remembered open "
                    f"action matching {close_target}."
                ),
                "action_memory",
            )

        return self._close_memory_entry(
            entry=named_entry,
            confirmation_handler=(
                confirmation_handler
            ),
            response_prefix=(
                "Closed remembered action"
            ),
        )

    def _try_fast_write_file_command(
        self,
        prompt: str,
        confirmation_handler: (
            ActionConfirmationHandler
            | None
        ),
    ) -> tuple[
        str,
        ToolRequest,
    ] | None:
        command = (
            self._parse_fast_write_file_command(
                prompt
            )
        )

        if command is None:
            return None

        try:
            result = (
                self._execute_tool_with_confirmation(
                    request=command.request,
                    confirmation_handler=(
                        confirmation_handler
                    ),
                )
            )

        except (
            FileNotFoundError,
            IsADirectoryError,
            NotADirectoryError,
            ValueError,
        ) as exc:
            return (
                (
                    "I understood the file request, but I "
                    f"could not write {command.target_label}: "
                    f"{exc}"
                ),
                command.request,
            )

        return (
            self._format_fast_command_result(
                request=command.request,
                result=result,
            ),
            command.request,
        )

    def _try_memory_list_command(
        self,
        normalized_prompt: str,
    ) -> tuple[
        str,
        str,
    ] | None:
        if (
            normalized_prompt
            not in _LIST_OPEN_ACTIONS_COMMANDS
        ):
            return None

        entries = (
            self.action_memory
            .open_entries()
        )

        if not entries:
            return (
                "I do not have any remembered open actions.",
                "action_memory",
            )

        labels = ", ".join(
            entry.label
            for entry in entries
        )

        return (
            f"I remember opening: {labels}.",
            "action_memory",
        )

    @staticmethod
    def _memory_close_target_from_prompt(
        prompt: str,
    ) -> str | None:
        match = (
            _CLOSE_REMEMBERED_ACTION_PATTERN
            .fullmatch(
                " ".join(
                    prompt
                    .strip()
                    .split()
                )
            )
        )

        if match is None:
            return None

        target = (
            match.group(
                "target"
            )
            .strip()
        )

        if not target:
            return None

        if (
            "last" in target.casefold()
            and "open" in target.casefold()
        ):
            return None

        return target

    def _close_memory_entry(
        self,
        *,
        entry: ActionMemoryEntry | None,
        confirmation_handler: (
            ActionConfirmationHandler
            | None
        ),
        response_prefix: str,
    ) -> tuple[
        str,
        str,
    ]:
        if entry is None:
            return (
                "I do not have an open action to close yet.",
                "action_memory",
            )

        try:
            self.tool_service.registry.get(
                entry.close_request.tool_name
            )

            self._execute_tool_with_confirmation(
                request=entry.close_request,
                confirmation_handler=(
                    confirmation_handler
                ),
            )

        except KeyError:
            return (
                (
                    "I remembered the action, but the "
                    "required close tool is not available."
                ),
                "action_memory",
            )

        except ValueError as exc:
            return (
                (
                    "I remembered the last thing I opened, "
                    f"but I could not close {entry.label}: "
                    f"{exc}"
                ),
                entry.close_request.tool_name,
            )

        self.action_memory.mark_closed(
            entry.entry_id,
            closed_at=time.time(),
        )

        return (
            (
                f"{response_prefix}: {entry.label}."
            ),
            entry.close_request.tool_name,
        )

    def _try_assistant_pack_command(
        self,
        prompt: str,
    ) -> str | None:
        normalized = " ".join(
            prompt
            .strip()
            .casefold()
            .split()
        )

        if not normalized:
            return None

        if normalized in _ASSISTANT_STATUS_COMMANDS:
            return self._format_assistant_status()

        if normalized in _ASSISTANT_BRIEFING_COMMANDS:
            return self._format_assistant_briefing()

        if normalized in _ASSISTANT_CAPABILITY_COMMANDS:
            return self._format_assistant_capabilities()

        if normalized in _ASSISTANT_PLAN_COMMANDS:
            return self._format_assistant_plan()

        if (
            normalized
            in _ASSISTANT_COMMAND_CENTER_COMMANDS
        ):
            return self._format_command_center()

        return None

    def _format_assistant_status(
        self,
    ) -> str:
        profile = (
            self._routing_profile()
        )

        main_model = (
            self._configured_model_label()
        )

        open_entries = (
            self.action_memory
            .open_entries()
        )

        last_route = (
            "none"
            if self._last_execution_telemetry is None
            else self._last_execution_telemetry.route
        )

        return "\n".join(
            [
                "JARVIS status:",
                f"- Mode: {profile.mode.value}",
                f"- Agent: {profile.agent_engine.value}",
                f"- Main model: {main_model}",
                (
                    "- Remembered open actions: "
                    f"{len(open_entries)}"
                ),
                f"- Last route: {last_route}",
                (
                    "- Safety: destructive and external actions "
                    "still require trusted tool permissions."
                ),
            ]
        )

    def _format_assistant_briefing(
        self,
    ) -> str:
        open_entries = (
            self.action_memory
            .open_entries()
        )

        if open_entries:
            opened = ", ".join(
                entry.label
                for entry in open_entries
            )

        else:
            opened = (
                "nothing remembered as currently open"
            )

        return "\n".join(
            [
                "JARVIS daily brief:",
                f"- Runtime: {self._configured_model_label()}",
                f"- Open actions I remember: {opened}.",
                (
                    "- Fast actions: open apps/sites, timed "
                    "open-wait-close, close remembered targets."
                ),
                (
                    "- Approval layer: active for configured "
                    "trusted tools."
                ),
                (
                    "- Next big modules: Gmail, calendar, "
                    "calls, CRM/outreach, and dashboard widgets."
                ),
            ]
        )

    @staticmethod
    def _format_assistant_capabilities(
    ) -> str:
        return (
            "JARVIS can now:\n"
            "- Use the OpenAI API directly for reasoning when configured.\n"
            "- Use local Ollama models or explicitly assigned Hermes agents.\n"
            "- Open known websites and applications quickly.\n"
            "- Save personal preferences: remember learning_goal = Spring Boot.\n"
            "- Inspect or remove preferences in Memory or with show memory.\n"
            "- Assign independent work in Tasks, with up to three concurrent jobs.\n"
            "- Delegate in chat: assign coder to chatgpt, then delegate to coder: your task.\n"
            "- Remember what it opened and close it later.\n"
            "- Close website tabs with a trusted close-tab action.\n"
            "- Route simple file writes through trusted local tools.\n"
            "- Route harder requests to the selected AI engine.\n"
            "- Ask for approval before configured sensitive actions.\n"
            "- Show status, briefing, and the product roadmap."
        )

    @staticmethod
    def _format_assistant_plan(
    ) -> str:
        return (
            "JARVIS product plan:\n"
            "1. Command center: status, briefing, memory, approvals.\n"
            "2. Connectors: Gmail, calendar, browser, files, phone.\n"
            "3. Background routines: morning brief and important alerts.\n"
            "4. Approval inbox: drafts/calls/messages wait for Salem.\n"
            "5. Super UI: Today, Tasks, Memory, Approvals, Logs, Voice.\n"
            "6. Commercial layer: name, installer, privacy, licensing."
        )

    def _format_command_center(
        self,
    ) -> str:
        profile = (
            self._routing_profile()
        )

        return "\n".join(
            [
                "JARVIS command center:",
                (
                    "- Brain: Hermes for conversation, planning, "
                    "and higher reasoning."
                ),
                (
                    "- Hands: trusted local tools for Windows, "
                    "browser tabs, files, approvals, and memory."
                ),
                (
                    "- Current runtime: "
                    f"{profile.agent_engine.value} / "
                    f"{profile.mode.value} / "
                    f"{self._configured_model_label()}."
                ),
                (
                    "- Try now: ask normally, open a website, "
                    "create a desktop note, then ask what I opened."
                ),
                (
                    "- Next build target: action cards, approval "
                    "inbox, Gmail/calendar connectors, and voice."
                ),
            ]
        )

    def _configured_model_label(
        self,
    ) -> str:
        if self.model_manager is not None:
            selection = (
                self.model_manager
                .profile()
                .model_for(
                    ModelRole.MAIN
                )
            )

            if selection is not None:
                return (
                    f"{selection.provider_id}/"
                    f"{selection.model_id}"
                )

        raw_model = getattr(
            self.model_provider,
            "model",
            None,
        )

        if isinstance(
            raw_model,
            str,
        ):
            return raw_model

        return self.model_provider.name

    def _parse_timed_open_close_command(
        self,
        prompt: str,
    ) -> TimedOpenCloseCommand | None:
        normalized = " ".join(
            prompt
            .strip()
            .split()
        )

        if not normalized:
            return None

        for pattern in _TIMED_OPEN_CLOSE_PATTERNS:
            match = pattern.fullmatch(
                normalized
            )

            if match is None:
                continue

            seconds = int(
                match.group(
                    "seconds"
                )
            )

            if (
                seconds
                > _MAX_TIMED_OPEN_CLOSE_SECONDS
            ):
                return None

            action = match.group(
                "action"
            )

            target = (
                match.group(
                    "target"
                )
                .strip()
            )

            open_request = (
                self.fast_command_router
                .route(
                    f"{action} {target}"
                )
            )

            if (
                open_request is None
                or open_request.tool_name
                not in {
                    "open_application",
                    "open_url",
                }
            ):
                return None

            close_target = (
                self._close_target_for_open_request(
                    open_request
                )
            )

            if close_target is None:
                return None

            return TimedOpenCloseCommand(
                open_request=open_request,
                seconds=seconds,
                close_target=close_target,
            )

        return None

    def _parse_fast_write_file_command(
        self,
        prompt: str,
    ) -> FastWriteFileCommand | None:
        normalized = " ".join(
            prompt
            .strip()
            .split()
        )

        if not normalized:
            return None

        lowered = (
            normalized
            .casefold()
        )

        if (
            "file" not in lowered
            and ".txt" not in lowered
            and ".md" not in lowered
        ):
            return None

        if not any(
            verb in lowered
            for verb in (
                "create",
                "make",
                "write",
                "put",
            )
        ):
            return None

        location_alias = (
            self._fast_write_location_alias(
                lowered
            )
        )

        if location_alias is None:
            return None

        content_instruction = (
            self._fast_write_content_instruction(
                normalized
            )
        )

        if content_instruction is None:
            return None

        filename = (
            self._fast_write_filename(
                normalized,
                content_instruction,
            )
        )

        if filename is None:
            return None

        path = (
            filename
            if not location_alias
            else str(
                Path(location_alias)
                / filename
            )
        )

        return FastWriteFileCommand(
            request=ToolRequest(
                tool_name="write_file",
                arguments={
                    "path": path,
                    "content": (
                        self._resolve_fast_write_content(
                            content_instruction
                        )
                    ),
                    "overwrite": False,
                },
            ),
            target_label=path,
        )

    @staticmethod
    def _fast_write_location_alias(
        lowered_prompt: str,
    ) -> str | None:
        for word, alias in (
            _FAST_WRITE_LOCATION_ALIASES
            .items()
        ):
            if re.search(
                rf"\b(?:my\s+)?{re.escape(word)}\b",
                lowered_prompt,
            ):
                return alias

        return None

    @staticmethod
    def _fast_write_content_instruction(
        prompt: str,
    ) -> str | None:
        for pattern in _FAST_WRITE_CONTENT_PATTERNS:
            match = pattern.search(
                prompt
            )

            if match is None:
                continue

            content = (
                match.group(
                    "content"
                )
                .strip()
                .strip("\"'")
            )

            if content:
                return content

        return None

    def _resolve_fast_write_content(
        self,
        content: str,
    ) -> str:
        if not self._fast_write_content_needs_generation(
            content
        ):
            return content

        return self._generate_fast_write_content(
            content
        )

    @staticmethod
    def _fast_write_content_needs_generation(
        content: str,
    ) -> bool:
        lowered = (
            content
            .casefold()
        )

        words = set(
            re.findall(
                r"[a-z0-9_-]+",
                lowered,
            )
        )

        if words.intersection(
            _GENERATIVE_FILE_CONTENT_TERMS
        ):
            return True

        return lowered.startswith(
            (
                "how to ",
                "what to ",
                "why ",
            )
        )

    def _generate_fast_write_content(
        self,
        content_instruction: str,
    ) -> str:
        response = (
            self.hermes_cloud_chat_agent_engine
            .run(
                prompt=(
                    "Write the exact file content for this "
                    "user request:\n\n"
                    f"{content_instruction}"
                ),
                system_prompt=(
                    "You generate useful file contents for "
                    "JARVIS. Return only the exact text that "
                    "should be written to the file. Do not "
                    "explain, do not wrap the answer in code "
                    "fences, and do not mention that you are "
                    "an AI."
                ),
                conversation=None,
                confirmation_handler=None,
            )
        )

        return (
            response
            .strip()
        )

    @staticmethod
    def _fast_write_filename(
        prompt: str,
        content_instruction: str,
    ) -> str | None:
        match = (
            _FAST_WRITE_FILENAME_PATTERN
            .search(
                prompt
            )
        )

        if match is None:
            return (
                JarvisApplication
                ._default_fast_write_filename(
                    prompt,
                    content_instruction,
                )
            )

        filename = (
            match.group(
                "filename"
            )
            .strip()
            .strip("\"'")
        )

        if not filename:
            return None

        candidate = Path(
            filename
        )

        if (
            candidate.is_absolute()
            or len(candidate.parts) != 1
        ):
            return None

        suffix = (
            candidate.suffix
            .casefold()
        )

        if not suffix:
            filename = (
                f"{filename}.txt"
            )

        elif (
            suffix
            not in _FAST_WRITE_FILE_EXTENSIONS
        ):
            return None

        return filename

    @staticmethod
    def _default_fast_write_filename(
        prompt: str,
        content_instruction: str,
    ) -> str:
        del prompt

        lowered = (
            content_instruction
            .casefold()
        )

        words = [
            word
            for word in re.findall(
                r"[a-z0-9]+",
                lowered,
            )
            if (
                word
                not in _FAST_WRITE_FILENAME_STOPWORDS
            )
        ]

        if "recipe" in words:
            subject_words = [
                word
                for word in words
                if word != "recipe"
            ]

            if subject_words:
                subject = (
                    subject_words[-1]
                )

                return (
                    f"{subject}-recipe.txt"
                )

            return "recipe.txt"

        return _DEFAULT_FAST_NOTE_FILENAME

    @staticmethod
    def _close_target_for_open_request(
        request: ToolRequest,
    ) -> str | None:
        if request.tool_name == "open_application":
            application = request.arguments.get(
                "application"
            )

            if isinstance(
                application,
                str,
            ):
                return application

            return None

        if request.tool_name != "open_url":
            return None

        url = request.arguments.get(
            "url"
        )

        if not isinstance(
            url,
            str,
        ):
            return None

        hostname = urlsplit(
            url
        ).hostname

        if hostname is None:
            return None

        normalized_hostname = (
            hostname
            .removeprefix(
                "www."
            )
        )

        close_target = (
            normalized_hostname
            .split(
                ".",
                1,
            )[0]
            .strip()
        )

        if not close_target:
            return None

        return close_target

    @staticmethod
    def _close_request_for_timed_open_close(
        command: TimedOpenCloseCommand,
    ) -> ToolRequest:
        return (
            JarvisApplication
            ._close_request_for_open_request(
                command.open_request
            )
        )

    @staticmethod
    def _close_request_for_open_request(
        request: ToolRequest,
    ) -> ToolRequest:
        close_target = (
            JarvisApplication
            ._close_target_for_open_request(
                request
            )
        )

        if close_target is None:
            raise ValueError(
                "Open request does not have a close target."
            )

        if request.tool_name == "open_url":
            return ToolRequest(
                tool_name="keyboard_action",
                arguments={
                    "window": close_target,
                    "action": "close_tab",
                },
            )

        return ToolRequest(
            tool_name="close_window",
            arguments={
                "window": close_target,
            },
        )

    def _remember_open_action(
        self,
        request: ToolRequest,
    ) -> ActionMemoryEntry | None:
        if request.tool_name not in {
            "open_application",
            "open_url",
        }:
            return None

        try:
            close_request = (
                self._close_request_for_open_request(
                    request
                )
            )

        except ValueError:
            return None

        return self.action_memory.remember_opened(
            label=(
                self._open_request_label(
                    request
                )
            ),
            open_request=request,
            close_request=close_request,
            opened_at=time.time(),
        )

    def _record_fast_command_telemetry(
        self,
        request: ToolRequest,
        duration_seconds: float,
    ) -> None:
        self._last_execution_telemetry = (
            ExecutionTelemetry(
                route="FAST COMMAND",
                engine="JARVIS trusted core",
                duration_seconds=duration_seconds,
                tool_name=request.tool_name,
                reason=(
                    "Deterministic FastCommandRouter match."
                ),
            )
        )

    def _record_fast_multistep_telemetry(
        self,
        tool_name: str,
        duration_seconds: float,
    ) -> None:
        self._last_execution_telemetry = (
            ExecutionTelemetry(
                route="FAST MULTI-STEP",
                engine="JARVIS trusted core",
                duration_seconds=duration_seconds,
                tool_name=tool_name,
                reason=(
                    "Deterministic timed open/close "
                    "command match."
                ),
            )
        )

    def _record_fast_memory_telemetry(
        self,
        tool_name: str,
        duration_seconds: float,
    ) -> None:
        self._last_execution_telemetry = (
            ExecutionTelemetry(
                route="FAST MEMORY",
                engine="JARVIS trusted core",
                duration_seconds=duration_seconds,
                tool_name=tool_name,
                reason=(
                    "Deterministic action-memory "
                    "follow-up command match."
                ),
            )
        )

    def _record_assistant_pack_telemetry(
        self,
        duration_seconds: float,
    ) -> None:
        self._last_execution_telemetry = (
            ExecutionTelemetry(
                route="ASSISTANT PACK",
                engine="JARVIS command center",
                duration_seconds=duration_seconds,
                tool_name="assistant_pack",
                reason=(
                    "Deterministic command-center "
                    "request match."
                ),
            )
        )

    def _record_agent_telemetry(
        self,
        decision: RouteDecision,
        engine: AgentEngine,
        duration_seconds: float,
    ) -> None:
        route = (
            self._telemetry_route_name(
                decision
            )
        )

        self._last_execution_telemetry = (
            ExecutionTelemetry(
                route=route,
                engine=(
                    self._telemetry_engine_name(
                        engine
                    )
                ),
                model=(
                    self._telemetry_model_name(
                        engine
                    )
                ),
                duration_seconds=duration_seconds,
                reason=decision.reason,
            )
        )

    @staticmethod
    def _telemetry_route_name(
        decision: RouteDecision,
    ) -> str:
        if (
            decision.target
            is RouteTarget.NATIVE
        ):
            return "NATIVE"

        if decision.use_cloud:
            if decision.use_tools:
                return "ACTION BRIDGE"

            return "CLOUD CHAT"

        if decision.use_tools:
            return "LOCAL ACTION"

        return "LOCAL HERMES"

    @staticmethod
    def _telemetry_engine_name(
        engine: AgentEngine,
    ) -> str:
        if isinstance(
            engine,
            HermesAgentEngine,
        ):
            if engine.gateway_url is not None:
                return "Hermes Gateway"

            if engine.tool_service is not None:
                return "Hermes CLI + JARVIS MCP"

            return "Hermes CLI"

        return engine.name

    def _telemetry_model_name(
        self,
        engine: AgentEngine,
    ) -> str | None:
        if isinstance(engine, NativeAgentEngine) and engine is not self.native_agent_engine:
            provider = engine.agent_service.model_provider
            return f"{provider.name}/{getattr(provider, 'model', 'default')}"

        if isinstance(
            engine,
            HermesAgentEngine,
        ):
            if engine.gateway_url is not None:
                return engine.gateway_model

            if engine.model is not None:
                return engine.model

            return "Hermes default"

        if self.model_manager is not None:
            selection = (
                self.model_manager
                .profile()
                .model_for(
                    ModelRole.MAIN
                )
            )

            if selection is not None:
                return (
                    f"{selection.provider_id}/"
                    f"{selection.model_id}"
                )

        raw_model = getattr(
            self.model_provider,
            "model",
            None,
        )

        if isinstance(
            raw_model,
            str,
        ):
            return raw_model

        return None

    @staticmethod
    def _format_fast_command_result(
        request: ToolRequest,
        result: object,
    ) -> str:
        if (
            request.tool_name
            == "open_application"
            and isinstance(
                result,
                dict,
            )
        ):
            application = result.get(
                "application"
            )

            if isinstance(
                application,
                str,
            ):
                return (
                    f"Opened {application}."
                )

        if (
            request.tool_name
            == "open_url"
            and isinstance(
                result,
                dict,
            )
        ):
            url = result.get(
                "url"
            )

            if isinstance(
                url,
                str,
            ):
                return (
                    f"Opened {url}."
                )

        if (
            request.tool_name
            == "write_file"
            and isinstance(
                result,
                dict,
            )
        ):
            path = result.get(
                "path"
            )

            if isinstance(
                path,
                str,
            ):
                return (
                    f"Wrote file: {path}."
                )

        return "Done."

    @staticmethod
    def _format_timed_open_close_result(
        command: TimedOpenCloseCommand,
        close_result: object,
    ) -> str:
        opened = (
            JarvisApplication
            ._open_request_label(
                command.open_request
            )
        )

        closed_window = (
            command.close_target
        )

        if isinstance(
            close_result,
            dict,
        ):
            window = close_result.get(
                "window"
            )

            if isinstance(
                window,
                str,
            ):
                closed_window = window

        return (
            f"Opened {opened}. "
            f"Waited {command.seconds} seconds, "
            f"then requested close for {closed_window}."
        )

    @staticmethod
    def _format_timed_open_close_failure(
        command: TimedOpenCloseCommand,
        error: ValueError,
    ) -> str:
        opened = (
            JarvisApplication
            ._open_request_label(
                command.open_request
            )
        )

        return (
            f"Opened {opened}. "
            f"Waited {command.seconds} seconds, "
            "but I could not close a matching window for "
            f"{command.close_target}: {error}"
        )

    @staticmethod
    def _open_request_label(
        request: ToolRequest,
    ) -> str:
        if request.tool_name == "open_url":
            url = request.arguments.get(
                "url"
            )

            if isinstance(
                url,
                str,
            ):
                return url

        if request.tool_name == "open_application":
            application = request.arguments.get(
                "application"
            )

            if isinstance(
                application,
                str,
            ):
                return application

        return "the target"

    # =================================================
    # MODEL / AGENT EXECUTION
    # =================================================

    def ask(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> ModelResponse:
        return self.model_provider.generate(
            ModelRequest(
                prompt=prompt,
                system_prompt=system_prompt,
            )
        )

    def ask_with_tools(
        self,
        prompt: str,
        system_prompt: str | None = None,
        confirmation_handler: ActionConfirmationHandler | None = None,
    ) -> str:
        self._last_execution_telemetry = None
        self._last_route_decision = None
        command = assistant_command(self, prompt)
        if command is not None:
            return command
        override_match = re.match(r"^@(local|chatgpt|hermes)\s+(.+)$", prompt.strip(), re.IGNORECASE | re.DOTALL)
        override = override_match[1].casefold() if override_match else None
        if override_match:
            prompt = override_match[2]
        context = self.personal_memory.context(prompt, include_recent=len(self.conversation) == 0)
        response = self._ask_with_tools(
            prompt, (system_prompt or "You are JARVIS, the user's personal assistant.") + context,
            confirmation_handler, agent_override=override,
        )
        self.personal_memory.remember_turn(prompt, response)
        return response

    def _run_independent_worker(self, worker: WorkerDefinition, prompt: str) -> str:
        if self._active_runtime_mode() is RuntimeMode.LOCAL and worker.backend != "local":
            raise ValueError("Local mode blocks cloud workers. Change the mode in Models first.")
        system = (
            f"You are JARVIS worker {worker.name}. Complete only the assigned task. "
            "You have no PC action tools. Do not claim to have opened, saved, browsed, "
            "or changed anything. Describe any missing access honestly.\n" + worker.instructions
            + self.personal_memory.context(prompt)
        )
        if worker.backend == "hermes":
            engine = self.hermes_cloud_chat_agent_engine
            self._ensure_engine_available(engine)
            # Independent tasks never receive the main chat history or action bridge.
            return engine.run(prompt=prompt, system_prompt=system, conversation=Conversation())
        provider = self.cloud_provider if worker.backend == "chatgpt" else self.local_worker_provider
        if provider is None:
            raise ValueError("OpenAI is not configured. Set JARVIS_OPENAI_API_KEY locally and restart JARVIS.")
        if worker.model:
            from jarvis.models.ollama import OllamaProvider
            from jarvis.models.openai_compatible import OpenAICompatibleProvider
            if isinstance(provider, OpenAICompatibleProvider):
                provider = OpenAICompatibleProvider(
                    provider_name=provider.name, model=worker.model, base_url=provider.base_url,
                    api_key=provider.api_key, timeout=provider.timeout, transport=provider.transport)
            elif isinstance(provider, OllamaProvider):
                provider = OllamaProvider(model=worker.model, base_url=provider.base_url)
        return provider.generate(ModelRequest(prompt=prompt, system_prompt=system)).text

    def shutdown(self) -> None:
        self.agent_team.shutdown()
        self.personal_memory.close()

    def _ask_with_tools(
        self,
        prompt: str,
        system_prompt: str | None = None,
        confirmation_handler: (
            ActionConfirmationHandler
            | None
        ) = None,
        agent_override: str | None = None,
    ) -> str:
        # -------------------------------------------------
        # STAGE 1
        #
        # Extremely simple trusted deterministic commands.
        # No model is involved.
        # -------------------------------------------------

        started_at = (
            time.perf_counter()
        )

        assistant_pack_response = (
            self._try_assistant_pack_command(
                prompt
            )
        )

        if assistant_pack_response is not None:
            self._last_route_decision = None

            self._record_assistant_pack_telemetry(
                duration_seconds=(
                    time.perf_counter()
                    - started_at
                ),
            )

            return assistant_pack_response

        fast_write_result = (
            self._try_fast_write_file_command(
                prompt=prompt,
                confirmation_handler=(
                    confirmation_handler
                ),
            )
        )

        if fast_write_result is not None:
            (
                fast_write_response,
                fast_write_request,
            ) = fast_write_result

            self._last_route_decision = None

            self._record_fast_command_telemetry(
                request=fast_write_request,
                duration_seconds=(
                    time.perf_counter()
                    - started_at
                ),
            )

            return fast_write_response

        fast_result = (
            self._try_fast_command(
                prompt=prompt,
                confirmation_handler=(
                    confirmation_handler
                ),
            )
        )

        if fast_result is not None:
            fast_response, fast_request = fast_result

            self._last_route_decision = None

            self._record_fast_command_telemetry(
                request=fast_request,
                duration_seconds=(
                    time.perf_counter()
                    - started_at
                ),
            )

            return fast_response

        timed_result = (
            self._try_timed_open_close_command(
                prompt=prompt,
                confirmation_handler=(
                    confirmation_handler
                ),
            )
        )

        if timed_result is not None:
            (
                timed_response,
                timed_tool_name,
            ) = timed_result

            self._last_route_decision = None

            self._record_fast_multistep_telemetry(
                tool_name=timed_tool_name,
                duration_seconds=(
                    time.perf_counter()
                    - started_at
                ),
            )

            return timed_response

        memory_result = (
            self._try_memory_close_command(
                prompt=prompt,
                confirmation_handler=(
                    confirmation_handler
                ),
            )
        )

        if memory_result is not None:
            (
                memory_response,
                memory_tool_name,
            ) = memory_result

            self._last_route_decision = None

            self._record_fast_memory_telemetry(
                tool_name=memory_tool_name,
                duration_seconds=(
                    time.perf_counter()
                    - started_at
                ),
            )

            return memory_response

        # -------------------------------------------------
        # STAGE 2
        #
        # Decide Native vs Hermes using runtime policy and
        # request complexity.
        # -------------------------------------------------

        engine = (
            self._route_agent_request(
                prompt, agent_override
            )
        )

        decision = self._last_route_decision

        started_at = (
            time.perf_counter()
        )

        try:
            return engine.run(
                prompt=prompt,
                system_prompt=system_prompt,
                conversation=self.conversation,
                confirmation_handler=(
                    confirmation_handler
                ),
            )

        finally:
            if decision is not None:
                self._record_agent_telemetry(
                    decision=decision,
                    engine=engine,
                    duration_seconds=(
                        time.perf_counter()
                        - started_at
                    ),
                )

    def new_conversation(
        self,
    ) -> None:
        self.conversation.clear()

    def conversation_message_count(
        self,
    ) -> int:
        return len(
            self.conversation
        )

    # =================================================
    # MODEL MANAGEMENT
    # =================================================

    def runtime_profile(
        self,
    ) -> RuntimeProfile:
        manager = (
            self._require_model_manager()
        )

        return manager.profile()

    def model_providers(
        self,
    ) -> tuple[
        ProviderDefinition,
        ...,
    ]:
        manager = (
            self._require_model_manager()
        )

        return manager.providers()

    def available_models(
        self,
    ) -> tuple[
        ModelDefinition,
        ...,
    ]:
        manager = (
            self._require_model_manager()
        )

        return manager.models()

    def models_for_provider(
        self,
        provider_id: str,
    ) -> tuple[
        ModelDefinition,
        ...,
    ]:
        manager = (
            self._require_model_manager()
        )

        return manager.models_for_provider(
            provider_id
        )

    def refresh_models(
        self,
        provider_id: str,
    ) -> tuple[
        ModelDefinition,
        ...,
    ]:
        manager = (
            self._require_model_manager()
        )

        return manager.refresh_provider(
            provider_id
        )

    def set_runtime_mode(
        self,
        mode: RuntimeMode,
    ) -> None:
        """
        Change intelligence mode.

        Explicit Hermes selections continue to update
        immediately.

        AUTO selections are resolved independently for each
        request by RequestRouter.
        """

        manager = (
            self._require_model_manager()
        )

        manager.set_mode(
            mode
        )

        self._activate_agent_engine(
            manager.profile().agent_engine
        )

    def set_agent_engine(
        self,
        agent_engine: AgentEngineId,
    ) -> None:
        manager = (
            self._require_model_manager()
        )

        # Validate explicit Hermes before persisting it.
        #
        # AUTO is evaluated per request and therefore does not
        # require Hermes merely to save the AUTO setting.
        if agent_engine is AgentEngineId.HERMES:
            candidate: AgentEngine

            if (
                manager.profile().mode
                in {
                    RuntimeMode.SMART,
                    RuntimeMode.MAXIMUM,
                }
            ):
                candidate = (
                    self.hermes_cloud_agent_engine
                )

            else:
                candidate = (
                    self.hermes_local_agent_engine
                )

            self._ensure_engine_available(
                candidate
            )

        manager.set_agent_engine(
            agent_engine
        )

        self._activate_agent_engine(
            agent_engine
        )

    def model_selection(
        self,
        role: ModelRole,
    ) -> ModelSelection | None:
        manager = (
            self._require_model_manager()
        )

        return (
            manager
            .profile()
            .model_for(
                role
            )
        )

    def set_model_for_role(
        self,
        role: ModelRole,
        provider_id: str,
        model_id: str,
    ) -> None:
        manager = (
            self._require_model_manager()
        )

        manager.set_model(
            role,
            provider_id,
            model_id,
        )

        if role is ModelRole.MAIN:
            self._activate_main_model()

    def _activate_main_model(
        self,
    ) -> None:
        """
        Rebuild Native and Hermes Local after changing MAIN.
        """

        manager = (
            self._require_model_manager()
        )

        provider = manager.build_provider(
            ModelRole.MAIN
        )

        self.model_provider = provider
        if provider.name == "openai":
            self.cloud_provider = provider
        elif provider.name == "ollama":
            self.local_worker_provider = provider

        self.agent_service = (
            self._build_agent_service(
                provider
            )
        )

        self.native_agent_engine = (
            NativeAgentEngine(
                self.agent_service
            )
        )

        self._rebuild_local_hermes_engine()

        self._activate_agent_engine(
            manager.profile().agent_engine
        )

    def _require_model_manager(
        self,
    ) -> ModelManager:
        if self.model_manager is None:
            raise RuntimeError(
                "Model management is not configured."
            )

        return self.model_manager

    # =================================================
    # CAPABILITY PERMISSIONS
    # =================================================

    def permission_decision(
        self,
        capability: Capability,
    ) -> PermissionDecision:
        return (
            self.tool_service
            .executor
            .policy
            .evaluate(
                capability
            )
        )

    def permission_mode(
        self,
        capability: Capability,
    ) -> PermissionMode:
        explicit_mode = (
            self._permission_modes.get(
                capability
            )
        )

        if explicit_mode is not None:
            return explicit_mode

        decision = (
            self.permission_decision(
                capability
            )
        )

        if decision is PermissionDecision.ALLOW:
            return PermissionMode.ALLOW_SESSION

        if (
            decision
            is PermissionDecision.REQUIRE_CONFIRMATION
        ):
            return PermissionMode.ASK

        return PermissionMode.DENY

    def set_permission_mode(
        self,
        capability: Capability,
        mode: PermissionMode,
    ) -> None:
        policy = (
            self.tool_service
            .executor
            .policy
        )

        policy.set_decision(
            capability,
            mode.to_decision(),
        )

        self._permission_modes[
            capability
        ] = mode

        if mode is PermissionMode.ALLOW_SESSION:
            self._persistent_permission_modes[
                capability
            ] = PermissionMode.ASK

            self._persist_permission_modes()

            return

        self._persistent_permission_modes[
            capability
        ] = mode

        self._persist_permission_modes()

    def _persist_permission_modes(
        self,
    ) -> None:
        if self.permission_mode_store is None:
            return

        self.permission_mode_store.save(
            self._persistent_permission_modes
        )

    # =================================================
    # FILESYSTEM SCOPES
    # =================================================

    def filesystem_read_scopes(
        self,
    ) -> tuple[
        Path,
        ...,
    ]:
        policy = (
            self._require_filesystem_scope_policy()
        )

        return policy.allowed_roots

    def filesystem_scope_persistence_enabled(
        self,
    ) -> bool:
        return (
            self.filesystem_scope_store
            is not None
        )

    def add_filesystem_read_scope(
        self,
        path: Path,
    ) -> None:
        policy = (
            self._require_filesystem_scope_policy()
        )

        policy.add_root(
            path
        )

        self._persist_filesystem_scopes()

    def remove_filesystem_read_scope(
        self,
        path: Path,
    ) -> None:
        policy = (
            self._require_filesystem_scope_policy()
        )

        policy.remove_root(
            path
        )

        self._persist_filesystem_scopes()

    def _persist_filesystem_scopes(
        self,
    ) -> None:
        if self.filesystem_scope_store is None:
            return

        policy = (
            self._require_filesystem_scope_policy()
        )

        additional_roots = [
            root
            for root in policy.allowed_roots
            if root != policy.workspace_root
        ]

        self.filesystem_scope_store.save(
            additional_roots
        )

    def _require_filesystem_scope_policy(
        self,
    ) -> FilesystemScopePolicy:
        if self.filesystem_scope_policy is None:
            raise RuntimeError(
                "Filesystem scope policy is not configured."
            )

        return self.filesystem_scope_policy
