from jarvis.bootstrap import build_application
from jarvis.core.config import load_settings
from jarvis.core.system_prompt import build_system_prompt
from jarvis.core.tool_request import ToolRequest
from jarvis.tools.executor import (
    ConfirmationRequiredError,
    PermissionDeniedError,
)


def main() -> None:
    """
    Temporary command-line interface for JARVIS.

    The CLI itself contains very little business logic.

    Real behavior lives inside:
    - JarvisApplication
    - AgentService
    - ToolService
    - PermissionPolicy
    """

    settings = load_settings()

    settings.workspace_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    app = build_application(
        settings
    )

    system_prompt = build_system_prompt(
        app.tool_service.registry,
    )

    print("JARVIS Core v0.1")

    print(
        f"Workspace: "
        f"{settings.workspace_dir.resolve()}"
    )

    print(
        "READ_FILE permission:",
        (
            "enabled"
            if settings.allow_read_file
            else "disabled"
        ),
    )

    print(
        "READ_SYSTEM_INFO permission:",
        (
            "enabled"
            if settings.allow_system_info
            else "disabled"
        ),
    )

    print(
        f"Model provider: "
        f"{settings.model_provider}"
    )

    print(
        f"Local model: "
        f"{settings.ollama_model}"
    )

    print(
        "Type 'help' to see available commands."
    )

    while True:
        command = input(
            "\njarvis> "
        ).strip()

        if not command:
            continue

        # -------------------------------------------------
        # Exit JARVIS
        # -------------------------------------------------

        if command in {
            "exit",
            "quit",
        }:
            print(
                "JARVIS shutting down."
            )
            break

        # -------------------------------------------------
        # Help
        # -------------------------------------------------

        if command == "help":
            print(
                "Available commands:"
            )

            print(
                "  status          "
                "Show JARVIS status"
            )

            print(
                "  ask <message>   "
                "Talk to JARVIS"
            )

            print(
                "  new             "
                "Start a new conversation"
            )

            print(
                "  system          "
                "Show basic computer information"
            )

            print(
                "  read <file>     "
                "Read a workspace file"
            )

            print(
                "  list [folder]   "
                "List workspace files"
            )

            print(
                "  exit            "
                "Exit JARVIS"
            )

            continue

        # -------------------------------------------------
        # Status
        # -------------------------------------------------

        if command == "status":
            print(
                "JARVIS Core is running."
            )

            print(
                "Conversation messages:",
                app.conversation_message_count(),
            )

            continue

        # -------------------------------------------------
        # Start a fresh chat
        # -------------------------------------------------

        if command == "new":
            app.new_conversation()

            print(
                "Started a new conversation."
            )

            continue

        # -------------------------------------------------
        # Natural-language JARVIS agent
        # -------------------------------------------------

        if command.startswith(
            "ask "
        ):
            prompt = command.removeprefix(
                "ask "
            ).strip()

            if not prompt:
                print(
                    "Please provide a message."
                )
                continue

            try:
                result = app.ask_with_tools(
                    prompt=prompt,
                    system_prompt=system_prompt,
                )

                print(result)

            except PermissionDeniedError:
                print(
                    "Permission denied by "
                    "JARVIS security policy."
                )

            except ConfirmationRequiredError:
                print(
                    "This action requires confirmation."
                )

            except KeyError as exc:
                print(
                    f"Unknown tool requested: {exc}"
                )

            except FileNotFoundError as exc:
                print(
                    f"File not found: {exc}"
                )

            except NotADirectoryError as exc:
                print(
                    f"Not a directory: {exc}"
                )

            except ValueError as exc:
                print(
                    f"Invalid request: {exc}"
                )

            except (
                RuntimeError,
                TypeError,
            ) as exc:
                print(
                    f"JARVIS error: {exc}"
                )

            continue

        # -------------------------------------------------
        # Direct system information command
        # -------------------------------------------------

        if command == "system":
            request = ToolRequest(
                tool_name="system_info",
            )

            try:
                result = app.execute_tool(
                    request
                )

                if isinstance(
                    result,
                    dict,
                ):
                    for key, value in result.items():
                        print(
                            f"{key}: {value}"
                        )

                else:
                    print(result)

            except PermissionDeniedError:
                print(
                    "Permission denied: "
                    "READ_SYSTEM_INFO is disabled."
                )

            except ConfirmationRequiredError:
                print(
                    "This action requires confirmation."
                )

            continue

        # -------------------------------------------------
        # Direct directory listing command
        # -------------------------------------------------

        if (
            command == "list"
            or command.startswith(
                "list "
            )
        ):
            path = command.removeprefix(
                "list"
            ).strip() or "."

            request = ToolRequest(
                tool_name="list_directory",
                arguments={
                    "path": path,
                },
            )

            try:
                result = app.execute_tool(
                    request
                )

                if isinstance(
                    result,
                    list,
                ):
                    for item in result:
                        print(item)

                else:
                    print(result)

            except PermissionDeniedError:
                print(
                    "Permission denied: "
                    "READ_FILE is disabled."
                )

            except ConfirmationRequiredError:
                print(
                    "This action requires confirmation."
                )

            except NotADirectoryError:
                print(
                    f"Not a directory: {path}"
                )

            except ValueError as exc:
                print(
                    f"Invalid request: {exc}"
                )

            continue

        # -------------------------------------------------
        # Direct file reading command
        # -------------------------------------------------

        if command.startswith(
            "read "
        ):
            path = command.removeprefix(
                "read "
            ).strip()

            request = ToolRequest(
                tool_name="read_file",
                arguments={
                    "path": path,
                },
            )

            try:
                result = app.execute_tool(
                    request
                )

                print(result)

            except PermissionDeniedError:
                print(
                    "Permission denied: "
                    "READ_FILE is disabled."
                )

            except ConfirmationRequiredError:
                print(
                    "This action requires confirmation."
                )

            except FileNotFoundError:
                print(
                    f"File not found: {path}"
                )

            except ValueError as exc:
                print(
                    f"Invalid request: {exc}"
                )

            continue

        print(
            "Unknown command. "
            "Type 'help'."
        )