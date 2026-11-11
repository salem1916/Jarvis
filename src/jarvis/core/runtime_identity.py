"""Current application facts, separate from user memory and model assumptions."""

import re


def voice_status_reply(prompt: str, source: str) -> str | None:
    text = re.sub(r"[^\w\s]", "", prompt.casefold()).strip()
    if source == "voice":
        text = re.sub(r"^how (?:am i|are you) listening(?: to (?:you|me))? ", "", text)
    if re.fullmatch(r"(?:(?:hey )?jarvis )?(?:can (?:you|i) hear (?:me|myself)(?: (?:clearly|clear|now))?|are you (?:listening|hearing me)|(?:check )?(?:microphone|audio|voice) status)", text):
        return "Yes, I heard you. Your words came through." if source == "voice" else "I received your typed message. Turn on Voice replies and use Talk or Listen to test your microphone."
    return None


def runtime_facts(app, source="text") -> dict:
    hub = app.intelligence
    prefs = hub.preferences() if hub else {}
    return {"identity": "Jarvis Windows desktop assistant", "input": source,
            "voice": "local Whisper transcription and Kokoro speech; the language model receives transcribed text",
            "screen_access": bool(app.screen_control_enabled),
            "ai_connection": prefs.get("source", getattr(app.model_provider, "name", "local")),
            "model": prefs.get("model", ""),
            "tools": {tool.name: app.permission_decision(tool.required_capability).value for tool in app.tool_service.registry.tools()}}


IDENTITY_RULES = (
    "You are Jarvis, the Windows desktop assistant speaking to its user. The model is one component of the app. "
    "Use the current runtime facts as authority about your capabilities, even when earlier assistant messages "
    "incorrectly said you cannot open apps or browse. Local speech and real Windows/browser tools belong to Jarvis. "
    "Do not describe yourself as a text-only chatbot with no app access. Voice input has already been transcribed "
    "by the app; acknowledge it naturally without pretending to assess acoustic quality. "
    "Be warm, direct and brief; no canned disclaimers or unnecessary follow-up question after every task. "
    "For actions, report only actual tool results. If a service fails, name the service and concrete problem. "
    "Screen access depends on the user's switch; permissions depend on the current capability decisions. "
    "Never invent live information or business figures. Memory stores user preferences, not new capabilities. "
)
