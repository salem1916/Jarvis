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
from jarvis.security.policy import PermissionDecision
from jarvis.tools.service import ToolService


class JarvisApplication:
    """
    Main application facade for JARVIS.

    CLI, Desktop UI, and future interfaces communicate
    through this class rather than reaching directly into
    tools, security, or model internals.
    """

    def __init__(
        self,
        tool_service: ToolService,
        model_provider: ModelProvider,
        filesystem_scope_policy: FilesystemScopePolicy | None = None,
        filesystem_scope_store: FilesystemScopeStore | None = None,
    ) -> None:
        self.tool_service = tool_service
        self.model_provider = model_provider

        self.filesystem_scope_policy = filesystem_scope_policy
        self.filesystem_scope_store = filesystem_scope_store

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
        Execute a direct tool request through JARVIS's
        trusted execution pipeline.
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

        request = ModelRequest(
            prompt=prompt,
            system_prompt=system_prompt,
        )

        return self.model_provider.generate(
            request
        )

    def ask_with_tools(
        self,
        prompt: str,
        system_prompt: str | None = None,
        confirmation_handler: ActionConfirmationHandler | None = None,
    ) -> str:
        """
        Main conversational agent path.

        A frontend may provide a trusted confirmation handler
        for actions requiring explicit human approval.
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

        Permission state remains unchanged.
        """

        self.conversation.clear()

    def conversation_message_count(
        self,
    ) -> int:
        """
        Return current internal conversation length.
        """

        return len(
            self.conversation
        )

    def permission_decision(
        self,
        capability: Capability,
    ) -> PermissionDecision:
        """
        Query the real capability security policy.
        """

        return self.tool_service.executor.policy.evaluate(
            capability
        )

    def filesystem_read_scopes(
        self,
    ) -> tuple[Path, ...]:
        """
        Return every currently approved read root.
        """

        policy = self._require_filesystem_scope_policy()

        return policy.allowed_roots

    def filesystem_scope_persistence_enabled(
        self,
    ) -> bool:
        """
        Return whether external filesystem scopes persist.
        """

        return self.filesystem_scope_store is not None

    def add_filesystem_read_scope(
        self,
        path: Path,
    ) -> None:
        """
        Grant read access to one additional directory.

        WRITE_FILE and DELETE_FILE remain separate.
        """

        policy = self._require_filesystem_scope_policy()

        policy.add_root(
            path
        )

        self._persist_filesystem_scopes()

    def remove_filesystem_read_scope(
        self,
        path: Path,
    ) -> None:
        """
        Remove a previously approved external read scope.
        """

        policy = self._require_filesystem_scope_policy()

        policy.remove_root(
            path
        )

        self._persist_filesystem_scopes()

    def _persist_filesystem_scopes(
        self,
    ) -> None:
        """
        Persist user-approved roots when configured.
        """

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
        """
        Return the configured filesystem scope policy.
        """

        if self.filesystem_scope_policy is None:
            raise RuntimeError(
                "Filesystem scope policy is not configured."
            )

        return self.filesystem_scope_policy