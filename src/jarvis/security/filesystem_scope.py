from collections.abc import Iterable
from pathlib import Path


class FilesystemScopePolicy:
    """
    Controls which filesystem locations JARVIS may read.

    Security requires BOTH:

        READ_FILE capability
                +
        approved filesystem scope

    The workspace always remains approved.

    User-approved folders may additionally include:

        Desktop
        Documents
        Downloads
        D:\\University
        custom project directories
    """

    def __init__(
        self,
        workspace_root: Path,
        allowed_roots: Iterable[Path] | None = None,
    ) -> None:
        self._workspace_root = (
            workspace_root
            .expanduser()
            .resolve()
        )

        self._allowed_roots: list[Path] = [
            self._workspace_root
        ]

        if allowed_roots is not None:
            for root in allowed_roots:
                self.add_root(
                    root
                )

    @property
    def workspace_root(
        self,
    ) -> Path:
        """
        Return the permanent workspace root.
        """

        return self._workspace_root

    @property
    def allowed_roots(
        self,
    ) -> tuple[Path, ...]:
        """
        Return all currently approved read roots.
        """

        return tuple(
            self._allowed_roots
        )

    def add_root(
        self,
        path: Path,
    ) -> None:
        """
        Grant read access to one existing directory.
        """

        resolved = (
            path
            .expanduser()
            .resolve()
        )

        if not resolved.exists():
            raise FileNotFoundError(
                f"Filesystem scope does not exist: {resolved}"
            )

        if not resolved.is_dir():
            raise NotADirectoryError(
                f"Filesystem scope is not a directory: {resolved}"
            )

        if resolved not in self._allowed_roots:
            self._allowed_roots.append(
                resolved
            )

    def remove_root(
        self,
        path: Path,
    ) -> None:
        """
        Remove a user-approved filesystem scope.

        The JARVIS workspace cannot be removed.
        """

        resolved = (
            path
            .expanduser()
            .resolve()
        )

        if resolved == self._workspace_root:
            raise ValueError(
                "The JARVIS workspace scope cannot be removed."
            )

        if resolved not in self._allowed_roots:
            raise ValueError(
                "Filesystem scope is not currently allowed: "
                f"{resolved}"
            )

        self._allowed_roots.remove(
            resolved
        )

    def is_allowed(
        self,
        path: Path,
    ) -> bool:
        """
        Return whether a path belongs to an approved scope.
        """

        resolved = (
            path
            .expanduser()
            .resolve()
        )

        return any(
            resolved == root
            or resolved.is_relative_to(
                root
            )
            for root in self._allowed_roots
        )

    def resolve_path(
        self,
        path: str | Path,
    ) -> Path:
        """
        Resolve a filesystem request safely.

        Absolute path:

            C:\\Users\\salem\\Desktop\\file.txt

        is accepted only if it belongs to an approved root.

        Normal relative path:

            hello.txt

        remains relative to the JARVIS workspace.

        NEW: approved-scope aliases are deterministic.

        If Desktop is approved:

            Desktop\\to learn.txt

        becomes:

            C:\\Users\\salem\\Desktop\\to learn.txt

        instead of:

            <workspace>\\Desktop\\to learn.txt
        """

        candidate = Path(
            path
        ).expanduser()

        if candidate.is_absolute():
            resolved = candidate.resolve()

        else:
            resolved = self._resolve_relative_path(
                candidate
            )

        if not self.is_allowed(
            resolved
        ):
            raise ValueError(
                "Path is outside the allowed filesystem scopes."
            )

        return resolved

    def _resolve_relative_path(
        self,
        candidate: Path,
    ) -> Path:
        """
        Resolve relative paths using approved-root aliases.

        Example approved roots:

            C:\\...\\workspace
            C:\\Users\\salem\\Desktop
            C:\\Users\\salem\\Documents

        Then:

            Desktop\\file.txt

        maps directly to the approved Desktop root.

        If no approved-root alias matches, the path keeps
        the original workspace-relative behavior.
        """

        parts = candidate.parts

        # "." or an empty relative path means workspace.
        if not parts:
            return self._workspace_root

        requested_alias = (
            parts[0]
            .casefold()
        )

        matching_roots = [
            root
            for root in self._allowed_roots
            if root.name.casefold()
            == requested_alias
        ]

        # -------------------------------------------------
        # One exact approved alias:
        #
        # Desktop\foo.txt
        #     ↓
        # C:\Users\...\Desktop\foo.txt
        # -------------------------------------------------

        if len(
            matching_roots
        ) == 1:
            root = matching_roots[0]

            remaining_parts = parts[
                1:
            ]

            return root.joinpath(
                *remaining_parts
            ).resolve()

        # -------------------------------------------------
        # More than one approved folder has the same name.
        #
        # We refuse to guess.
        # -------------------------------------------------

        if len(
            matching_roots
        ) > 1:
            raise ValueError(
                "Filesystem scope alias is ambiguous. "
                "Use an exact absolute path."
            )

        # -------------------------------------------------
        # No approved alias:
        #
        # Preserve existing workspace-relative behavior.
        # -------------------------------------------------

        return (
            self._workspace_root
            / candidate
        ).resolve()