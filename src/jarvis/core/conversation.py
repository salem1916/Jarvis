from jarvis.models.base import ModelMessage


class Conversation:
    """
    In-memory conversation state for one JARVIS chat.

    This stores the real model conversation:

        system
        user
        assistant
        tool
        assistant
        user
        ...

    For now this lives only in RAM.

    Later JARVIS will persist conversations in the
    database so chats can survive application restarts.
    """

    def __init__(self) -> None:
        self._messages: list[ModelMessage] = []

    def snapshot(self) -> list[ModelMessage]:
        """
        Return an independent copy of the conversation.

        AgentService works on this copy first.

        Only after an agent request completes successfully
        do we replace the real conversation history.

        That prevents a failed tool call or model error
        from leaving the conversation half-finished.
        """

        return [
            message.model_copy(deep=True)
            for message in self._messages
        ]

    def replace(
        self,
        messages: list[ModelMessage],
    ) -> None:
        """
        Replace the stored conversation with a completed
        conversation state.
        """

        self._messages = [
            message.model_copy(deep=True)
            for message in messages
        ]

    def clear(self) -> None:
        """
        Start a fresh conversation.
        """

        self._messages.clear()

    def __len__(self) -> int:
        """
        Number of messages currently stored.
        """

        return len(self._messages)