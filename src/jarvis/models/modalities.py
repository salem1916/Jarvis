"""Known text-only connections use Windows accessibility rather than image payloads."""


def supports_screen_images(provider) -> bool:
    delegate = getattr(provider, "delegate", provider)
    model = str(getattr(delegate, "model", "")).casefold()
    return not model.startswith(("openai/gpt-oss", "gpt-oss", "llama-3", "qwen/qwen3-32b", "qwen3-32b"))
