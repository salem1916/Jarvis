import json
import os
import shutil
import subprocess
from json import JSONDecodeError
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from jarvis.agents.base import AgentEngine
from jarvis.agents.hermes_bridge import (
    JarvisHermesBridge,
)
from jarvis.core.action_confirmation import (
    ActionConfirmationHandler,
)
from jarvis.core.conversation import Conversation
from jarvis.models.base import ModelMessage
from jarvis.tools.service import ToolService


class HermesAgentError(RuntimeError):
    """
    Raised when Hermes cannot complete a JARVIS request.
    """


class HermesAgentEngine(AgentEngine):
    """
    JARVIS adapter for Hermes Agent.

    Supported execution paths:

        Persistent Hermes Gateway
        -> fast cloud chat/reasoning
        -> no fresh Hermes process per request

        Hermes CLI subprocess
        -> trusted JARVIS MCP action path
        -> local Hermes/Ollama path
        -> compatibility fallback

    JARVIS remains responsible for trusted action execution,
    permissions, confirmations, and Windows control.
    """

    name = "hermes"

    def __init__(
        self,
        tool_service: ToolService | None = None,
        executable: str = "hermes",
        timeout: float = 180.0,
        provider: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        gateway_url: str | None = None,
        gateway_api_key: str | None = None,
        gateway_model: str = "hermes-agent",
    ) -> None:
        if not executable.strip():
            raise ValueError(
                "Hermes executable cannot be empty."
            )

        if timeout <= 0:
            raise ValueError(
                "Hermes timeout must be greater than zero."
            )

        if (
            provider is None
            and model is not None
        ):
            raise ValueError(
                "A Hermes provider is required when "
                "a model override is configured."
            )

        if (
            provider is not None
            and model is None
        ):
            raise ValueError(
                "A Hermes model is required when "
                "a provider override is configured."
            )

        if (
            gateway_url is not None
            and not gateway_url.strip()
        ):
            raise ValueError(
                "Hermes gateway URL cannot be empty."
            )

        if not gateway_model.strip():
            raise ValueError(
                "Hermes gateway model cannot be empty."
            )

        self.tool_service = tool_service
        self.executable = executable
        self.timeout = timeout

        self.provider = provider
        self.model = model

        self.base_url = base_url
        self.api_key = api_key

        self.gateway_url = (
            gateway_url.rstrip("/")
            if gateway_url is not None
            else None
        )

        self.gateway_api_key = (
            gateway_api_key
        )

        self.gateway_model = (
            gateway_model
        )

    def is_available(
        self,
    ) -> bool:
        """
        Return whether this Hermes execution path is configured.

        A persistent gateway does not require JARVIS to launch
        the Hermes executable itself.
        """

        if self.gateway_url is not None:
            return True

        return (
            shutil.which(
                self.executable
            )
            is not None
        )

    def run(
        self,
        prompt: str,
        system_prompt: str | None = None,
        conversation: Conversation | None = None,
        confirmation_handler: ActionConfirmationHandler | None = None,
    ) -> str:
        result = self._run_once(prompt, system_prompt, conversation, confirmation_handler)
        if conversation is not None:
            messages = [m for m in conversation.snapshot() if m.role != "system"]
            if system_prompt:
                messages.insert(0, ModelMessage(role="system", content=system_prompt))
            messages.extend([
                ModelMessage(role="user", content=prompt),
                ModelMessage(role="assistant", content=result),
            ])
            conversation.replace(messages)
        return result

    def _run_once(
        self,
        prompt: str,
        system_prompt: str | None = None,
        conversation: Conversation | None = None,
        confirmation_handler: (
            ActionConfirmationHandler
            | None
        ) = None,
    ) -> str:
        """
        Execute one request through Hermes.

        Persistent gateway is used only by engines explicitly
        configured with gateway_url.

        Trusted action/local engines continue using the existing
        CLI path until the JARVIS MCP bridge itself becomes a
        persistent service.
        """

        if not prompt.strip():
            raise ValueError(
                "Hermes prompt cannot be empty."
            )

        if self.gateway_url is not None:
            return self._run_gateway(
                prompt=prompt,
                system_prompt=system_prompt,
                conversation=conversation,
            )

        if not self.is_available():
            raise HermesAgentError(
                "Hermes Agent is not installed or "
                "is not available on PATH."
            )

        hermes_prompt = self._build_prompt(
            prompt=prompt,
            system_prompt=system_prompt,
            conversation=conversation,
            tools_available=(
                self.tool_service
                is not None
            ),
        )

        # Standalone/test mode:
        #
        # no trusted JARVIS ToolService exists, therefore
        # Hermes receives only the harmless todo toolset.
        if self.tool_service is None:
            return self._run_process(
                hermes_prompt=hermes_prompt,
                toolset="todo",
            )

        # Real JARVIS action mode:
        #
        # expose only the trusted JARVIS MCP bridge.
        with JarvisHermesBridge(
            tool_service=self.tool_service,
            confirmation_handler=confirmation_handler,
        ):
            return self._run_process(
                hermes_prompt=hermes_prompt,
                toolset="jarvis",
            )

    def _run_gateway(
        self,
        prompt: str,
        system_prompt: str | None,
        conversation: Conversation | None = None,
    ) -> str:
        """
        Send one chat request to the already-running Hermes
        Gateway API.

        This removes the per-message Hermes process startup cost.
        """

        if self.gateway_url is None:
            raise HermesAgentError(
                "Hermes gateway is not configured."
            )

        messages: list[
            dict[
                str,
                str,
            ]
        ] = []

        if (
            system_prompt is not None
            and system_prompt.strip()
        ):
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt.strip(),
                }
            )

        if conversation is not None:
            messages.extend(
                {"role": m.role, "content": m.content}
                for m in conversation.snapshot()
                if m.role in {"user", "assistant"} and m.content
            )

        messages.append(
            {
                "role": "user",
                "content": prompt.strip(),
            }
        )

        payload = {
            "model": self.gateway_model,
            "messages": messages,
            "stream": False,
        }

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

        if self.gateway_api_key:
            headers[
                "Authorization"
            ] = (
                "Bearer "
                f"{self.gateway_api_key}"
            )

        request = Request(
            (
                f"{self.gateway_url}"
                "/v1/chat/completions"
            ),
            data=json.dumps(
                payload
            ).encode(
                "utf-8"
            ),
            headers=headers,
            method="POST",
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout,
            ) as response:
                raw_response = (
                    response.read()
                )

        except HTTPError as exc:
            detail = self._read_http_error(
                exc
            )

            raise HermesAgentError(
                "Hermes Gateway rejected the request"
                f"{detail}."
            ) from exc

        except (
            URLError,
            TimeoutError,
            OSError,
        ) as exc:
            raise HermesAgentError(
                "Hermes Gateway is unavailable. "
                "Start it with 'hermes gateway' and "
                "verify JARVIS_HERMES_GATEWAY_KEY."
            ) from exc

        try:
            decoded = json.loads(
                raw_response.decode(
                    "utf-8"
                )
            )

        except (
            UnicodeDecodeError,
            JSONDecodeError,
        ) as exc:
            raise HermesAgentError(
                "Hermes Gateway returned invalid JSON."
            ) from exc

        if not isinstance(
            decoded,
            dict,
        ):
            raise HermesAgentError(
                "Hermes Gateway returned an invalid response."
            )

        choices = decoded.get(
            "choices"
        )

        if (
            not isinstance(
                choices,
                list,
            )
            or not choices
        ):
            raise HermesAgentError(
                "Hermes Gateway returned no choices."
            )

        first_choice = choices[
            0
        ]

        if not isinstance(
            first_choice,
            dict,
        ):
            raise HermesAgentError(
                "Hermes Gateway returned an invalid choice."
            )

        message = first_choice.get(
            "message"
        )

        if not isinstance(
            message,
            dict,
        ):
            raise HermesAgentError(
                "Hermes Gateway returned an invalid message."
            )

        content = message.get(
            "content"
        )

        if (
            not isinstance(
                content,
                str,
            )
            or not content.strip()
        ):
            raise HermesAgentError(
                "Hermes Gateway returned an empty response."
            )

        return content.strip()

    @staticmethod
    def _read_http_error(
        error: HTTPError,
    ) -> str:
        """
        Extract a short safe error detail without exposing secrets.
        """

        try:
            raw = error.read()

        except OSError:
            raw = b""

        if not raw:
            return (
                f" with HTTP {error.code}"
            )

        try:
            text = raw.decode(
                "utf-8",
                errors="replace",
            ).strip()

        except OSError:
            text = ""

        if not text:
            return (
                f" with HTTP {error.code}"
            )

        if len(text) > 300:
            text = (
                text[:300]
                + "..."
            )

        return (
            f" with HTTP {error.code}: {text}"
        )

    def _run_process(
        self,
        hermes_prompt: str,
        toolset: str,
    ) -> str:
        """
        Run one Hermes CLI request.

        Provider/model arguments are added only when this
        engine has an explicit override.

        Therefore the normal cloud Hermes engine continues
        using the user's existing Hermes configuration.
        """

        command = [
            self.executable,
            "-z",
            hermes_prompt,
            "--no-restore-cwd",
            "--ignore-rules",
            "--toolsets",
            toolset,
        ]

        if self.provider is not None:
            command.extend(
                [
                    "--provider",
                    self.provider,
                ]
            )

        if self.model is not None:
            command.extend(
                [
                    "--model",
                    self.model,
                ]
            )

        environment: (
            dict[
                str,
                str,
            ]
            | None
        ) = None

        if (
            self.base_url is not None
            or self.api_key is not None
        ):
            environment = os.environ.copy()

            if self.base_url is not None:
                environment[
                    "OPENAI_BASE_URL"
                ] = self.base_url

            if self.api_key is not None:
                environment[
                    "OPENAI_API_KEY"
                ] = self.api_key

        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                shell=False,
                env=environment,
            )

        except subprocess.TimeoutExpired as exc:
            raise HermesAgentError(
                "Hermes exceeded the configured timeout."
            ) from exc

        except OSError as exc:
            raise HermesAgentError(
                "JARVIS could not start Hermes Agent."
            ) from exc

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()

        if completed.returncode != 0:
            detail = (
                stderr
                or stdout
                or "No error details were returned."
            )

            raise HermesAgentError(
                "Hermes Agent failed: "
                f"{detail}"
            )

        if not stdout:
            raise HermesAgentError(
                "Hermes Agent returned an empty response."
            )

        return stdout

    @staticmethod
    def _build_prompt(
        prompt: str,
        system_prompt: str | None,
        conversation: Conversation | None,
        tools_available: bool,
    ) -> str:
        """
        Build a privacy-conscious Hermes CLI request.

        Existing JARVIS conversation history is intentionally
        not forwarded yet.

        Later the router will explicitly decide what context
        each local/cloud provider is allowed to receive.
        """

        del conversation

        sections: list[str] = []

        if system_prompt:
            sections.append(

                    "[JARVIS SYSTEM INSTRUCTIONS]\n"
                    f"{system_prompt.strip()}"

            )

        if tools_available:
            sections.append(
                """
[JARVIS TRUSTED TOOL INSTRUCTIONS]

You are operating inside JARVIS.

For Windows application and UI actions, use the JARVIS MCP
tools.

Call list_jarvis_tools when you need exact available tool
names or schemas.

Then call execute_jarvis_tool using the exact JARVIS tool
name and exact arguments.

Continue until the complete user request has actually been
executed.

Observation is not execution.

Opening an application does not satisfy a request that also
asks you to interact with that application.

Do not claim an action succeeded unless the trusted JARVIS
tool result confirms it.

Do not use a terminal, shell, direct filesystem access,
Hermes computer-use, or another execution mechanism.

JARVIS permissions and confirmations are authoritative.
""".strip()
            )

        sections.append(

                "[CURRENT USER REQUEST]\n"
                f"{prompt.strip()}"

        )

        return "\n\n".join(
            sections
        )
