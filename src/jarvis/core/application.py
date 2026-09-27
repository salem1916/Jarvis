from pathlib import Path

from jarvis.core.action_confirmation import ActionConfirmationHandler
from jarvis.core.agent_service import AgentService
from jarvis.core.conversation import Conversation
from jarvis.core.tool_request import ToolRequest
from jarvis.models.base import (
    ModelProvider,
    ModelRequest,
    ModelResponse,
)
from jarvis.security.capabilities import Capability
from jarvis.security.filesystem_scope import FilesystemScopePolicy
from jarvis.security.filesystem_scope_store import FilesystemScopeStore
from jarvis.security.permission_mode import PermissionMode
from jarvis.security.permission_mode_store import PermissionModeStore
from jarvis.security.policy import (
    PermissionDecision,
)
from jarvis.tools.service import ToolService


class JarvisApplication:
    """
    Main trusted application facade for JARVIS.
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
    ) -> None:
        self.tool_service = tool_service
        self.model_provider = model_provider

        self.filesystem_scope_policy = filesystem_scope_policy
        self.filesystem_scope_store = filesystem_scope_store

        self.permission_mode_store = permission_mode_store

        self._permission_modes = dict(
            permission_modes or {}
        )

        # Persistent fallback state is kept separately.
        #
        # ALLOW_SESSION never belongs here.
        self._persistent_permission_modes = {
            capability: mode
            for capability, mode
            in self._permission_modes.items()
            if mode is not PermissionMode.ALLOW_SESSION
        }

        self.agent_service = AgentService(
            model_provider=model_provider,
            tool_service=tool_service,
        )

        self.conversation = Conversation()

    def execute_tool(
        self,
        request: ToolRequest,
        *,
        confirmed: bool = False,
    ) -> object:
        """
        Execute a trusted structured tool request.
        """

        return self.tool_service.execute(
            request,
            confirmed=confirmed,
        )

    def ask(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> ModelResponse:
        """
        Perform a stateless model request.
        """

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
        """
        Main conversational agent path.
        """

        return self.agent_service.run(
            prompt=prompt,
            system_prompt=system_prompt,
            conversation=self.conversation,
            confirmation_handler=confirmation_handler,
        )

    def new_conversation(
        self,
    ) -> None:
        """
        Clear conversation history only.
        """

        self.conversation.clear()

    def conversation_message_count(
        self,
    ) -> int:
        return len(
            self.conversation
        )

    # =================================================
    # CAPABILITY PERMISSIONS
    # =================================================

    def permission_decision(
        self,
        capability: Capability,
    ) -> PermissionDecision:
        """
        Return the effective low-level policy decision.
        """

        return self.tool_service.executor.policy.evaluate(
            capability
        )

    def permission_mode(
        self,
        capability: Capability,
    ) -> PermissionMode:
        """
        Return the human-facing permission mode.

        For capabilities not explicitly managed through the
        mode system, derive a sensible value from the current
        PermissionPolicy.
        """

        explicit_mode = self._permission_modes.get(
            capability
        )

        if explicit_mode is not None:
            return explicit_mode

        decision = self.permission_decision(
            capability
        )

        if decision is PermissionDecision.ALLOW:
            return PermissionMode.ALLOW_SESSION

        if decision is PermissionDecision.REQUIRE_CONFIRMATION:
            return PermissionMode.ASK

        return PermissionMode.DENY

    def set_permission_mode(
        self,
        capability: Capability,
        mode: PermissionMode,
    ) -> None:
        """
        Change one capability's permission mode.

        This API is trusted application state.

        The AI model has no tool that can call it.
        """

        policy = self.tool_service.executor.policy

        policy.set_decision(
            capability,
            mode.to_decision(),
        )

        self._permission_modes[
            capability
        ] = mode

        # ---------------------------------------------
        # Session-only:
        #
        # allow now, but return to ASK next restart.
        # ---------------------------------------------

        if mode is PermissionMode.ALLOW_SESSION:
            self._persistent_permission_modes[
                capability
            ] = PermissionMode.ASK

            self._persist_permission_modes()

            return

        # ---------------------------------------------
        # Deny / Ask / Always Allow survive restart.
        # ---------------------------------------------

        self._persistent_permission_modes[
            capability
        ] = mode

        self._persist_permission_modes()

    def _persist_permission_modes(
        self,
    ) -> None:
        """
        Save permission preferences if persistence is enabled.
        """

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
    ) -> tuple[Path, ...]:
        policy = self._require_filesystem_scope_policy()

        return policy.allowed_roots

    def filesystem_scope_persistence_enabled(
        self,
    ) -> bool:
        return self.filesystem_scope_store is not None

    def add_filesystem_read_scope(
        self,
        path: Path,
    ) -> None:
        policy = self._require_filesystem_scope_policy()

        policy.add_root(
            path
        )

        self._persist_filesystem_scopes()

    def remove_filesystem_read_scope(
        self,
        path: Path,
    ) -> None:
        policy = self._require_filesystem_scope_policy()

        policy.remove_root(
            path
        )

        self._persist_filesystem_scopes()

    def _persist_filesystem_scopes(
        self,
    ) -> None:
        if self.filesystem_scope_store is None:
            return

        policy = self._require_filesystem_scope_policy()

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