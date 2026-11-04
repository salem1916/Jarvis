def main() -> None:
    # Optional processes (including local speech) can import their own modules
    # without importing the entire desktop and its Windows automation stack.
    from jarvis.cli import main as run

    run()

__all__ = ["main"]
