from jarvis.core.conversation import Conversation
from jarvis.models.base import ModelMessage


def test_conversation_stores_messages() -> None:
    """
    A conversation should preserve messages
    that are committed to it.
    """

    conversation = Conversation()

    conversation.replace(
        [
            ModelMessage(
                role="user",
                content="Hello",
            ),
            ModelMessage(
                role="assistant",
                content="Hello Salem",
            ),
        ]
    )

    messages = conversation.snapshot()

    assert len(messages) == 2

    assert messages[0].content == "Hello"

    assert messages[1].content == "Hello Salem"


def test_conversation_can_be_cleared() -> None:
    """
    Starting a new conversation should remove
    previous chat history.
    """

    conversation = Conversation()

    conversation.replace(
        [
            ModelMessage(
                role="user",
                content="Hello",
            )
        ]
    )

    assert len(conversation) == 1

    conversation.clear()

    assert len(conversation) == 0
    