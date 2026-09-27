from collections.abc import Iterable
from pathlib import Path


class FilesystemScopePolicy:
    """
    Controls which filesystem locations JARVIS may read.

    The workspace is always an allowed root.

    Additional directories may be granted later by the user.

    Example:

        workspace
        Documents
        Downloads
        C:\\Projects

    A path is allowed only when its fully-resolved path is
    inside one of these approved roots.

    Resolving paths first also protects against:

    - ../ path traversal
    - absolute paths outside approved roots
    - symlinks that escape an approved directory
    """

    def __init__(
        self,
        workspace_root: Path,
        allowed_roots: Iterable[Path] | None = None,
    ) -> None:
        self._workspace_root = workspace_root.expanduser().resolve()

        self._allowed_roots: list[Path] = [
            self._workspace_root
        ]

        if allowed_roots is not None:
            for root in allowed_roots:
                self.add_root(root)

    @property
    def workspace_root(self) -> Path:
        """
        Return the permanent JARVIS workspace root.
        """

        return self._workspace_root

    @property
    def allowed_roots(self) -> tuple[Path, ...]:
        """
        Return the currently approved read scopes.

        A tuple prevents callers from directly modifying
        our internal list.
        """

        return tuple(
            self._allowed_roots
        )

    def add_root(
        self,
        path: Path,
    ) -> None:
        """
        Grant JARVIS read access to one directory.

        The directory must already exist.

        Adding the same directory twice is harmless.
        """

        resolved = path.expanduser().resolve()

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
        Remove one previously granted filesystem scope.

        The permanent JARVIS workspace cannot be removed.
        """

        resolved = path.expanduser().resolve()

        if resolved == self._workspace_root:
            raise ValueError(
                "The JARVIS workspace scope cannot be removed."
            )

        if resolved not in self._allowed_roots:
            raise ValueError(
                f"Filesystem scope is not currently allowed: {resolved}"
            )

        self._allowed_roots.remove(
            resolved
        )

    def is_allowed(
        self,
        path: Path,
    ) -> bool:
        """
        Return True when a resolved path is inside at least
        one approved filesystem root.
        """

        resolved = path.expanduser().resolve()

        return any(
            resolved == root
            or resolved.is_relative_to(root)
            for root in self._allowed_roots
        )

    def resolve_path(
        self,
        path: str | Path,
    ) -> Path:
        """
        Resolve a requested path and enforce scope rules.

        Relative paths continue to mean:

            relative to the JARVIS workspace

        Absolute paths are accepted only when they are
        inside an explicitly approved root.
        """

        candidate = Path(
            path
        ).expanduser()

        if not candidate.is_absolute():
            candidate = (
                self._workspace_root
                / candidate
            )

        resolved = candidate.resolve()

        if not self.is_allowed(
            resolved
        ):
            raise ValueError(
                "Path is outside the allowed filesystem scopes."
            )

        return resolved
        