from pathlib import Path

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
from jarvis.security.policy import PermissionDecision
from jarvis.tools.service import ToolService


class JarvisApplication:
    """
    Main application facade for JARVIS.

    Interfaces such as:

    - CLI
    - desktop UI
    - future mobile/dashboard interfaces

    communicate with this class rather than directly
    controlling security, models, or tools.
    """

    def __init__(
        self,
        tool_service: ToolService,
        model_provider: ModelProvider,
        filesystem_scope_policy: FilesystemScopePolicy | None = None,
    ) -> None:
        self.tool_service = tool_service
        self.model_provider = model_provider

        self.filesystem_scope_policy = filesystem_scope_policy

        self.agent_service = AgentService(
            model_provider=model_provider,
            tool_service=tool_service,
        )

        self.conversation = Conversation()

    def execute_tool(
        self,
        request: ToolRequest,
    ) -> object:
        """
        Execute a direct tool request through JARVIS's
        trusted security pipeline.
        """

        return self.tool_service.execute(
            request
        )

    def ask(
        self,
        prompt: str,
        system_prompt: str | None = None,
    ) -> ModelResponse:
        """
        Perform a simple stateless model request.
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
    ) -> str:
        """
        Main conversational JARVIS path.
        """

        return self.agent_service.run(
            prompt=prompt,
            system_prompt=system_prompt,
            conversation=self.conversation,
        )

    def new_conversation(self) -> None:
        """
        Start a fresh in-memory conversation.
        """

        self.conversation.clear()

    def conversation_message_count(self) -> int:
        """
        Return the current internal conversation length.
        """

        return len(
            self.conversation
        )

    def permission_decision(
        self,
        capability: Capability,
    ) -> PermissionDecision:
        """
        Query the real security policy.
        """

        return self.tool_service.executor.policy.evaluate(
            capability
        )

    def filesystem_read_scopes(
        self,
    ) -> tuple[Path, ...]:
        """
        Return every directory JARVIS may currently read.
        """

        policy = self._require_filesystem_scope_policy()

        return policy.allowed_roots

    def add_filesystem_read_scope(
        self,
        path: Path,
    ) -> None:
        """
        Grant read access to one additional directory.

        This changes only filesystem scope.

        It does NOT grant WRITE_FILE or DELETE_FILE.
        """

        policy = self._require_filesystem_scope_policy()

        policy.add_root(
            path
        )

    def remove_filesystem_read_scope(
        self,
        path: Path,
    ) -> None:
        """
        Remove one previously granted read scope.

        The permanent workspace cannot be removed.
        """

        policy = self._require_filesystem_scope_policy()

        policy.remove_root(
            path
        )

    def _require_filesystem_scope_policy(
        self,
    ) -> FilesystemScopePolicy:
        """
        Return the configured filesystem scope policy.

        A missing policy indicates an incorrectly assembled
        application rather than a user permission problem.
        """

        if self.filesystem_scope_policy is None:
            raise RuntimeError(
                "Filesystem scope policy is not configured."
            )

        return self.filesystem_scope_policy