"""A single model request for plain reasoning; avoids an agent loop and tool schemas."""

from jarvis.agents.base import AgentEngine
from jarvis.core.action_confirmation import ActionConfirmationHandler
from jarvis.core.conversation import Conversation
from jarvis.core.request_control import check_cancelled
from jarvis.models.base import ModelMessage, ModelProvider, ModelRequest


class ReasoningAgentEngine(AgentEngine):
    name = "direct"

    def __init__(self, provider: ModelProvider) -> None:
        self.provider = provider

    def run(self, prompt: str, system_prompt: str | None = None,
            conversation: Conversation | None = None,
            confirmation_handler: ActionConfirmationHandler | None = None) -> str:
        check_cancelled()
        history = [] if conversation is None else conversation.snapshot()
        if system_prompt and "JARVIS currently provides these REAL tools:" in system_prompt:
            # The desktop's action prompt lists every tool; plain reasoning needs none of it.
            persona = system_prompt.split("JARVIS currently provides these REAL tools:", 1)[0]
            memory = ("[JARVIS PERSONAL CONTEXT]" + system_prompt.split("[JARVIS PERSONAL CONTEXT]", 1)[1]
                      if "[JARVIS PERSONAL CONTEXT]" in system_prompt else "")
            concise = "Prefer concise replies unless detail is requested." if "Prefer concise, direct replies" in system_prompt else ""
            behavior = ("[JARVIS ASSISTANT BEHAVIOR]" + system_prompt.split("[JARVIS ASSISTANT BEHAVIOR]", 1)[1].split("[JARVIS PERSONAL CONTEXT]", 1)[0]
                        if "[JARVIS ASSISTANT BEHAVIOR]" in system_prompt else "")
            system_prompt = (
                persona + "This is a conversation turn; Jarvis's separate action controller executes real tools. "
                "Do not confuse this API request with the whole application's capabilities. "
                "Do not claim a new action happened without a trusted result. " + concise + "\n" + behavior + "\n" + memory
            )
        # Tool-call fragments never cross into this no-tools reasoning path.
        messages = [m for m in history if m.role in {"user", "assistant"} and m.content][-20:]
        if system_prompt:
            messages.insert(0, ModelMessage(role="system", content=system_prompt))
        messages.append(ModelMessage(role="user", content=prompt))
        response = self.provider.generate(ModelRequest(prompt=prompt, messages=messages))
        check_cancelled()
        if response.tool_calls:
            raise ValueError("This reasoning connection requested a tool it does not have. Use the main action route.")
        messages.append(ModelMessage(role="assistant", content=response.text))
        if conversation is not None:
            conversation.replace(messages)
        return response.text
