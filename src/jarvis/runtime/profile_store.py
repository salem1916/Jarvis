import json
from pathlib import Path

from pydantic import ValidationError

from jarvis.runtime.profile import RuntimeProfile


class RuntimeProfileStore:
    """
    Persist the user's JARVIS runtime choices.

    Example location:

        %APPDATA%\\Jarvis\\runtime_profile.json

    This file may contain:

        - runtime mode
        - selected agent engine
        - provider/model selections

    It must NEVER contain API keys or other secrets.
    """

    VERSION = 1

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = path

    def load(
        self,
    ) -> RuntimeProfile:
        """
        Load the saved runtime profile.

        If no profile exists yet, return a clean AUTO profile.
        """

        if not self.path.exists():
            return RuntimeProfile()

        try:
            raw_text = self.path.read_text(
                encoding="utf-8"
            )

            payload = json.loads(
                raw_text
            )

        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:
            raise ValueError(
                "Could not read the JARVIS runtime profile."
            ) from exc

        if not isinstance(
            payload,
            dict,
        ):
            raise TypeError(
                "Runtime profile must contain a JSON object."
            )

        version = payload.get(
            "version"
        )

        if version != self.VERSION:
            raise ValueError(
                "Unsupported runtime profile version: "
                f"{version}"
            )

        profile_data = payload.get(
            "profile"
        )

        if not isinstance(
            profile_data,
            dict,
        ):
            raise TypeError(
                "Runtime profile has no valid profile object."
            )

        try:
            return RuntimeProfile.model_validate(
                profile_data
            )

        except ValidationError as exc:
            raise ValueError(
                "Runtime profile contains invalid settings."
            ) from exc

    def save(
        self,
        profile: RuntimeProfile,
    ) -> None:
        """
        Atomically save the runtime profile.
        """

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "version": self.VERSION,
            "profile": profile.model_dump(
                mode="json"
            ),
        }

        temporary_path = self.path.with_suffix(
            self.path.suffix + ".tmp"
        )

        temporary_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary_path.replace(
            self.path
        )