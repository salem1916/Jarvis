import json
from collections.abc import Iterable
from pathlib import Path


class FilesystemScopeStore:
    """
    Persist user-approved filesystem read scopes.

    This store contains ONLY additional approved folders.

    The permanent JARVIS workspace is controlled separately
    by FilesystemScopePolicy and is not saved here.

    Example stored JSON:

        {
          "version": 1,
          "read_scopes": [
            "C:\\\\Users\\\\salem\\\\Desktop",
            "C:\\\\Users\\\\salem\\\\Documents"
          ]
        }
    """

    VERSION = 1

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = path.expanduser()

    def load(
        self,
    ) -> tuple[Path, ...]:
        """
        Load existing approved folders.

        Folders that no longer exist are ignored rather than
        preventing JARVIS from starting.
        """

        if not self.path.exists():
            return ()

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
                "Could not load persisted filesystem scopes."
            ) from exc

        # The JSON root must be an object/dictionary.
        #
        # This is a type problem, so TypeError is the
        # semantically correct exception.
        if not isinstance(
            payload,
            dict,
        ):
            raise TypeError(
                "Filesystem scope store must contain an object."
            )

        version = payload.get(
            "version"
        )

        if version != self.VERSION:
            raise ValueError(
                "Unsupported filesystem scope store version."
            )

        raw_scopes = payload.get(
            "read_scopes"
        )

        # read_scopes must be a JSON array/list.
        #
        # Again, this is a type mismatch rather than an
        # invalid numeric/value range.
        if not isinstance(
            raw_scopes,
            list,
        ):
            raise TypeError(
                "Filesystem scope store has invalid read_scopes."
            )

        loaded: list[Path] = []

        for raw_scope in raw_scopes:
            # Ignore malformed individual entries instead
            # of preventing JARVIS from starting.
            if not isinstance(
                raw_scope,
                str,
            ):
                continue

            scope = (
                Path(
                    raw_scope
                )
                .expanduser()
                .resolve()
            )

            # A previously approved drive/folder may have
            # disappeared since the previous JARVIS session.
            if not scope.is_dir():
                continue

            if scope not in loaded:
                loaded.append(
                    scope
                )

        return tuple(
            loaded
        )

    def save(
        self,
        scopes: Iterable[Path],
    ) -> None:
        """
        Atomically save approved read scopes.

        We first write a temporary file and then replace
        the previous state file.

        This reduces the chance of leaving a corrupted
        permissions file if writing is interrupted.
        """

        unique_scopes: list[str] = []

        for scope in scopes:
            resolved = (
                scope
                .expanduser()
                .resolve()
            )

            serialized = str(
                resolved
            )

            if serialized not in unique_scopes:
                unique_scopes.append(
                    serialized
                )

        payload = {
            "version": self.VERSION,
            "read_scopes": unique_scopes,
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

        # Replace the previous state file only after
        # the new temporary file has been written.
        temporary_path.replace(
            self.path
        )