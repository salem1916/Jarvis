from jarvis.tools.registry import ToolRegistry


def build_system_prompt(
    registry: ToolRegistry,
) -> str:
    """
    Build JARVIS's system prompt from the tools that
    are actually registered in the application.

    This prevents the model from assuming imaginary
    capabilities.
    """

    tool_lines = "\n".join(
        f"- {tool.name}: {tool.description}"
        for tool in registry.tools()
    )

    return (
        "You are JARVIS, Salem's personal AI assistant.\n"
        "Be helpful, concise, and accurate.\n\n"

        "The JARVIS application currently provides "
        "these tools:\n"
        f"{tool_lines}\n\n"

        "The provided tools are your legitimate way "
        "to access JARVIS capabilities.\n"

        "When the user asks for information that an "
        "available tool can provide, request that tool.\n"

        "Never fabricate or guess the result of a tool.\n"

        "Never claim that you read a file, listed a "
        "directory, inspected the computer, or performed "
        "any other action unless JARVIS actually provides "
        "the corresponding tool result.\n"

        "Do not claim capabilities that are not available "
        "through the JARVIS application."
    )