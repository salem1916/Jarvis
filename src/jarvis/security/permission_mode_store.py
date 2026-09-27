import json
from collections.abc import Mapping
from pathlib import Path

from jarvis.security.capabilities import Capability
from jarvis.security.permission_mode import PermissionMode


class PermissionModeStore:
    """
    Persist user-selected capability permission modes.

    Example:

        {
          "version": 1,
          "capabilities": {
            "WRITE_FILE": "always_allow",
            "DELETE_FILE": "ask"
          }
        }

    ALLOW_SESSION is never persisted.
    """

    VERSION = 1

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = path.expanduser()

    def load(
        self,
    ) -> dict[Capability, PermissionMode]:
        """
        Load persisted permission choices.
        """

        if not self.path.exists():
            return {}

        try:
            payload = json.loads(
                self.path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise ValueError(
                "Could not load persisted permission modes."
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise TypeError(
                "Permission mode store must contain an object."
            )

        if payload.get(
            "version"
        ) != self.VERSION:
            raise ValueError(
                "Unsupported permission mode store version."
            )

        raw_capabilities = payload.get(
            "capabilities"
        )

        if not isinstance(
            raw_capabilities,
            dict,
        ):
            raise TypeError(
                "Permission mode store has invalid capabilities."
            )

        result: dict[
            Capability,
            PermissionMode,
        ] = {}

        for (
            raw_capability,
            raw_mode,
        ) in raw_capabilities.items():
            if not isinstance(
                raw_capability,
                str,
            ):
                continue

            if not isinstance(
                raw_mode,
                str,
            ):
                continue

            try:
                capability = Capability(
                    raw_capability
                )

                mode = PermissionMode(
                    raw_mode
                )

            except ValueError:
                # Ignore values from capabilities/modes this
                # version of JARVIS does not understand.
                continue

            # Session-only access must never survive restart.
            if mode is PermissionMode.ALLOW_SESSION:
                continue

            result[
                capability
            ] = mode

        return result

    def save(
        self,
        modes: Mapping[
            Capability,
            PermissionMode,
        ],
    ) -> None:
        """
        Save persistent permission choices atomically.
        """

        serialized: dict[
            str,
            str,
        ] = {}

        for capability, mode in modes.items():
            if mode is PermissionMode.ALLOW_SESSION:
                raise ValueError(
                    "ALLOW_SESSION cannot be persisted."
                )

            serialized[
                capability.value
            ] = mode.value

        payload = {
            "version": self.VERSION,
            "capabilities": serialized,
        }

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporary_path = self.path.with_name(
            f"{self.path.name}.tmp"
        )

        temporary_path.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        temporary_path.replace(
            self.path
        )