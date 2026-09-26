from jarvis.bootstrap import build_application
from jarvis.core.config import load_settings
from jarvis.core.tool_request import ToolRequest
from jarvis.tools.executor import (
    ConfirmationRequiredError,
    PermissionDeniedError,
)


def main() -> None:
    settings = load_settings()

    settings.workspace_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    app = build_application(settings)

    print("JARVIS Core v0.1")
    print(f"Workspace: {settings.workspace_dir.resolve()}")
    print(
        "READ_FILE permission:",
        "enabled" if settings.allow_read_file else "disabled",
    )
    print(
        "READ_SYSTEM_INFO permission:",
        "enabled" if settings.allow_system_info else "disabled",
    )
    print("Type 'help' to see available commands.")

    while True:
        command = input("\njarvis> ").strip()

        if not command:
            continue

        if command in {"exit", "quit"}:
            print("JARVIS shutting down.")
            break

        if command == "help":
            print("Available commands:")
            print("  status          Show JARVIS status")
            print("  system          Show basic computer information")
            print("  read <file>     Read a file from the workspace")
            print("  list [folder]   List files in the workspace")
            print("  exit            Exit JARVIS")
            continue

        if command == "status":
            print("JARVIS Core is running.")
            continue

        if command == "system":
            request = ToolRequest(
                tool_name="system_info",
            )

            try:
                result = app.execute_tool(request)

                if isinstance(result, dict):
                    for key, value in result.items():
                        print(f"{key}: {value}")
                else:
                    print(result)

            except PermissionDeniedError:
                print("Permission denied: READ_SYSTEM_INFO is disabled.")

            except ConfirmationRequiredError:
                print("This action requires confirmation.")

            continue

        if command == "list" or command.startswith("list "):
            path = command.removeprefix("list").strip() or "."

            request = ToolRequest(
                tool_name="list_directory",
                arguments={"path": path},
            )

            try:
                result = app.execute_tool(request)

                if isinstance(result, list):
                    for item in result:
                        print(item)
                else:
                    print(result)

            except PermissionDeniedError:
                print("Permission denied: READ_FILE is disabled.")

            except ConfirmationRequiredError:
                print("This action requires confirmation.")

            except NotADirectoryError:
                print(f"Not a directory: {path}")

            except ValueError as exc:
                print(f"Invalid request: {exc}")

            continue

        if command.startswith("read "):
            path = command.removeprefix("read ").strip()

            request = ToolRequest(
                tool_name="read_file",
                arguments={"path": path},
            )

            try:
                result = app.execute_tool(request)
                print(result)

            except PermissionDeniedError:
                print("Permission denied: READ_FILE is disabled.")

            except ConfirmationRequiredError:
                print("This action requires confirmation.")

            except FileNotFoundError:
                print(f"File not found: {path}")

            except ValueError as exc:
                print(f"Invalid request: {exc}")

            continue

        print("Unknown command. Type 'help'.")