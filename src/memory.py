"""Message / ChatHistory, reused from the conversation-loop lab. 
Retrieved chunks never go in here — inject fresh each turn.

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
    def __init__(self, role: str, content: str):
        self.role = role
        self.content = content

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


class ChatHistory:
    def __init__(self):
        self.messages: list[Message] = []

    def add_turn(self, question: str, answer: str) -> None:
        """Append a completed user-assistant exchange, then drop anything that
        no longer fits the window.

        The useful context is the last few turns (which car, which symptom), 
        and a dropped turn costs less than a 
        summarization call on every long chat.
        Swap in summarized memory later if a demo ever needs it.
        """
        self.messages.append(Message("user", question))
        self.messages.append(Message("assistant", answer))
        self.messages = self.messages[-MAX_MESSAGES:]

    def to_list(self) -> list[dict]:
        return [message.to_dict() for message in self.messages]

    def clear(self) -> None:
        self.messages = []

    def __len__(self) -> int:
        return len(self.messages)
