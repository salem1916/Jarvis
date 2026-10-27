import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from jarvis.core.tool_request import ToolRequest


@dataclass(
    frozen=True,
    slots=True,
)
class ActionMemoryEntry:
    """
    One trusted action JARVIS performed and can later refer to.

    The entry stores only structured action metadata, not page
    contents, user text, credentials, or model responses.
    """

    entry_id: int
    label: str
    open_request: ToolRequest
    close_request: ToolRequest
    opened_at: float
    closed_at: float | None = None

    @property
    def is_open(
        self,
    ) -> bool:
        return self.closed_at is None

    def closed(
        self,
        closed_at: float,
    ) -> ActionMemoryEntry:
        return ActionMemoryEntry(
            entry_id=self.entry_id,
            label=self.label,
            open_request=self.open_request,
            close_request=self.close_request,
            opened_at=self.opened_at,
            closed_at=closed_at,
        )

    def to_dict(
        self,
    ) -> dict[str, object]:
        return {
            "entry_id": self.entry_id,
            "label": self.label,
            "open_request": _request_to_dict(
                self.open_request
            ),
            "close_request": _request_to_dict(
                self.close_request
            ),
            "opened_at": self.opened_at,
            "closed_at": self.closed_at,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, object],
    ) -> ActionMemoryEntry | None:
        entry_id = data.get(
            "entry_id"
        )

        label = data.get(
            "label"
        )

        opened_at = data.get(
            "opened_at"
        )

        closed_at = data.get(
            "closed_at"
        )

        open_request = _request_from_dict(
            data.get(
                "open_request"
            )
        )

        close_request = _request_from_dict(
            data.get(
                "close_request"
            )
        )

        if not isinstance(
            entry_id,
            int,
        ):
            return None

        if not isinstance(
            label,
            str,
        ):
            return None

        if not isinstance(
            opened_at,
            int | float,
        ):
            return None

        if (
            closed_at is not None
            and not isinstance(
                closed_at,
                int | float,
            )
        ):
            return None

        if (
            open_request is None
            or close_request is None
        ):
            return None

        return cls(
            entry_id=entry_id,
            label=label,
            open_request=open_request,
            close_request=close_request,
            opened_at=float(
                opened_at
            ),
            closed_at=(
                None
                if closed_at is None
                else float(
                    closed_at
                )
            ),
        )


class ActionMemory:
    """
    Short-term memory for trusted actions performed by JARVIS.

    It helps JARVIS understand follow-up commands like:

        close the last thing you opened

    without granting the model any new authority.
    """

    def __init__(
        self,
        *,
        store_path: Path | None = None,
        entries: tuple[
            ActionMemoryEntry,
            ...,
        ] = (),
        max_entries: int = 100,
    ) -> None:
        self.store_path = store_path
        self.max_entries = max_entries

        self._entries: list[
            ActionMemoryEntry
        ] = list(
            entries
        )

        self._next_entry_id = (
            max(
                (
                    entry.entry_id
                    for entry in self._entries
                ),
                default=0,
            )
            + 1
        )

    @classmethod
    def load(
        cls,
        store_path: Path,
        *,
        max_entries: int = 100,
    ) -> ActionMemory:
        if not store_path.exists():
            return cls(
                store_path=store_path,
                max_entries=max_entries,
            )

        try:
            raw = json.loads(
                store_path.read_text(
                    encoding="utf-8"
                )
            )

        except (
            OSError,
            json.JSONDecodeError,
        ):
            return cls(
                store_path=store_path,
                max_entries=max_entries,
            )

        if not isinstance(
            raw,
            dict,
        ):
            return cls(
                store_path=store_path,
                max_entries=max_entries,
            )

        raw_entries = raw.get(
            "entries",
            [],
        )

        if not isinstance(
            raw_entries,
            list,
        ):
            raw_entries = []

        entries: list[
            ActionMemoryEntry
        ] = []

        for raw_entry in raw_entries:
            if not isinstance(
                raw_entry,
                dict,
            ):
                continue

            entry = (
                ActionMemoryEntry
                .from_dict(
                    raw_entry
                )
            )

            if entry is not None:
                entries.append(
                    entry
                )

        return cls(
            store_path=store_path,
            entries=tuple(
                entries[
                    -max_entries:
                ]
            ),
            max_entries=max_entries,
        )

    def remember_opened(
        self,
        *,
        label: str,
        open_request: ToolRequest,
        close_request: ToolRequest,
        opened_at: float,
    ) -> ActionMemoryEntry:
        entry = ActionMemoryEntry(
            entry_id=self._next_entry_id,
            label=label,
            open_request=(
                self._copy_request(
                    open_request
                )
            ),
            close_request=(
                self._copy_request(
                    close_request
                )
            ),
            opened_at=opened_at,
        )

        self._next_entry_id += 1

        self._entries.append(
            entry
        )

        self._trim()
        self._save()

        return entry

    def last_open_entry(
        self,
    ) -> ActionMemoryEntry | None:
        for entry in reversed(
            self._entries
        ):
            if entry.is_open:
                return entry

        return None

    def open_entries(
        self,
    ) -> tuple[
        ActionMemoryEntry,
        ...,
    ]:
        return tuple(
            entry
            for entry in self._entries
            if entry.is_open
        )

    def find_open_entry(
        self,
        query: str,
    ) -> ActionMemoryEntry | None:
        normalized_query = (
            self._normalize_match_text(
                query
            )
        )

        if not normalized_query:
            return None

        matches = tuple(
            entry
            for entry in reversed(
                self._entries
            )
            if (
                entry.is_open
                and normalized_query
                in self._match_terms(
                    entry
                )
            )
        )

        if len(
            matches
        ) != 1:
            return None

        return matches[0]

    def mark_closed(
        self,
        entry_id: int,
        *,
        closed_at: float,
    ) -> ActionMemoryEntry | None:
        for index, entry in enumerate(
            self._entries
        ):
            if entry.entry_id != entry_id:
                continue

            closed_entry = entry.closed(
                closed_at
            )

            self._entries[
                index
            ] = closed_entry

            self._save()

            return closed_entry

        return None

    def entries(
        self,
    ) -> tuple[
        ActionMemoryEntry,
        ...,
    ]:
        return tuple(
            self._entries
        )

    def _trim(
        self,
    ) -> None:
        if len(
            self._entries
        ) <= self.max_entries:
            return

        self._entries = self._entries[
            -self.max_entries:
        ]

    def _save(
        self,
    ) -> None:
        if self.store_path is None:
            return

        self.store_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        payload = {
            "version": 1,
            "entries": [
                entry.to_dict()
                for entry in self._entries
            ],
        }

        self.store_path.write_text(
            json.dumps(
                payload,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

    @staticmethod
    def _copy_request(
        request: ToolRequest,
    ) -> ToolRequest:
        return ToolRequest(
            tool_name=request.tool_name,
            arguments=dict(
                request.arguments
            ),
        )

    @classmethod
    def _match_terms(
        cls,
        entry: ActionMemoryEntry,
    ) -> set[str]:
        terms = {
            cls._normalize_match_text(
                entry.label
            ),
        }

        open_request = entry.open_request

        if open_request.tool_name == "open_application":
            application = (
                open_request.arguments.get(
                    "application"
                )
            )

            if isinstance(
                application,
                str,
            ):
                terms.add(
                    cls._normalize_match_text(
                        application
                    )
                )

        if open_request.tool_name == "open_url":
            url = open_request.arguments.get(
                "url"
            )

            if isinstance(
                url,
                str,
            ):
                terms.update(
                    cls._url_match_terms(
                        url
                    )
                )

        close_window = (
            entry.close_request
            .arguments
            .get(
                "window"
            )
        )

        if isinstance(
            close_window,
            str,
        ):
            terms.add(
                cls._normalize_match_text(
                    close_window
                )
            )

        return {
            term
            for term in terms
            if term
        }

    @classmethod
    def _url_match_terms(
        cls,
        url: str,
    ) -> set[str]:
        terms = {
            cls._normalize_match_text(
                url
            )
        }

        hostname = urlsplit(
            url
        ).hostname

        if hostname is None:
            return terms

        clean_hostname = (
            hostname
            .removeprefix(
                "www."
            )
        )

        terms.add(
            cls._normalize_match_text(
                clean_hostname
            )
        )

        terms.add(
            cls._normalize_match_text(
                clean_hostname.split(
                    ".",
                    1,
                )[0]
            )
        )

        return terms

    @staticmethod
    def _normalize_match_text(
        value: str,
    ) -> str:
        return " ".join(
            value
            .strip()
            .casefold()
            .split()
        )


def _request_to_dict(
    request: ToolRequest,
) -> dict[str, object]:
    return {
        "tool_name": request.tool_name,
        "arguments": dict(
            request.arguments
        ),
    }


def _request_from_dict(
    value: object,
) -> ToolRequest | None:
    if not isinstance(
        value,
        dict,
    ):
        return None

    tool_name = value.get(
        "tool_name"
    )

    arguments = value.get(
        "arguments"
    )

    if not isinstance(
        tool_name,
        str,
    ):
        return None

    if not isinstance(
        arguments,
        dict,
    ):
        return None

    safe_arguments: dict[
        str,
        Any,
    ] = {
        str(
            key
        ): argument
        for key, argument in arguments.items()
    }

    return ToolRequest(
        tool_name=tool_name,
        arguments=safe_arguments,
    )
