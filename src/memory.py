"""Message / ChatHistory, reused from the conversation-loop lab. Retrieved chunks never go in here — inject fresh each turn.

The model is stateless: it forgets the instant it responds. "Memory" is just the
list of past turns re-sent on every request, which is all these two classes are.

What does NOT live here is as important as what does. No system prompt, no
retrieved chunks — history stays plain user/assistant turns. rag.py assembles
those extras in front of the history on each call and lets them fall away, or
five turns of top-k chunks eat the whole context window.
"""

# A turn is two messages, so this is ~10 turns. Long enough that the condenser
# has real history to resolve "it" against, short enough that the prompt can't
# grow without bound over a long session.
MAX_MESSAGES = 20


class Message:
    """One turn in the conversation. Becomes a dict at API call time."""

    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}

    def __repr__(self) -> str:
        return f"Message(role={self.role!r}, content={self.content[:40]!r}...)"


class ChatHistory:
    """An ordered list of Messages. Becomes a list of dicts at API call time."""

    def __init__(self, max_messages: int = MAX_MESSAGES):
        self.messages: list[Message] = []
        self.max_messages = max_messages

    def add(self, message: Message) -> None:
        self.messages.append(message)
        self._trim()

    def add_turn(self, question: str, answer: str) -> None:
        """Append a completed user/assistant exchange."""
        self.add(Message("user", question))
        self.add(Message("assistant", answer))

    def to_list(self) -> list[dict]:
        return [message.to_dict() for message in self.messages]

    def clear(self) -> None:
        self.messages = []

    def _trim(self) -> None:
        """Drop the oldest messages once the window is full.

        Oldest-first rather than the lab's summarize-and-reset: for a repair Q&A
        the useful context is the last few turns (which car, which symptom), and
        a dropped turn costs less than a summarization call on every long chat.
        Swap in summarized memory later if a demo ever needs it.
        """
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages :]

    def __len__(self) -> int:
        return len(self.messages)
