"""Gradio chat UI wrapping rag.ask(question, history).

Run from the project root:

    python src/app.py

The browser twin of main.py — same twenty lines of glue, different I/O. Like
main.py it owns the interface and nothing else: rag.py still has no idea this
file exists.

One wrinkle the CLI doesn't have: Gradio owns the transcript. It hands the whole
message list back on every turn, so rather than keeping a second copy of the
conversation in a module-level ChatHistory (which would leak across browser tabs
anyway, since every visitor shares the process), this rebuilds a fresh
ChatHistory from what Gradio displays. Retry, undo and edit then work for free —
they change what's on screen, and what's on screen *is* the history.
"""

import os

import gradio as gr

from memory import ChatHistory
from rag import ask

DESCRIPTION = """\
Ask about symptoms, repairs, recalls, or modifications for the 2017-2024 Audi A4.

Answers are grounded in a small corpus of NHTSA complaints, owner threads, CARB
EO listings and manual excerpts. When the sources don't cover a question the
assistant says so instead of inventing a torque spec.
"""

EXAMPLES = [
    "My B9 is burning oil between changes. Is that a known problem?",
    "What are the common carbon buildup symptoms on the 2.0T?",
    "Are there any open recalls on the 2018 A4?",
    "Is a catback exhaust CARB legal for this car?",
]


def to_chat_history(messages: list[dict]) -> ChatHistory:
    """Rebuild a ChatHistory from Gradio's message list.

    Pairs user messages with the assistant reply that follows so each one goes
    through `add_turn` — that keeps the MAX_MESSAGES trimming in memory.py in
    charge of the window instead of duplicating the rule here. An unanswered
    trailing user message is skipped; it's the question being asked right now,
    and rag.ask() appends it itself.
    """
    history = ChatHistory()

    for message, following in zip(messages, messages[1:]):
        if message["role"] == "user" and following["role"] == "assistant":
            history.add_turn(message["content"], following["content"])

    return history


def respond(question: str, messages: list[dict]) -> str:
    """The Gradio callback. Everything real happens inside ask()."""
    try:
        return ask(question, to_chat_history(messages))
    except Exception as error:
        # gr.Error surfaces a toast and leaves the failed turn out of the
        # transcript — the same "keep history intact" behaviour as main.py,
        # since here the transcript IS the history.
        raise gr.Error(f"Something went wrong: {error}")


demo = gr.ChatInterface(
    fn=respond,
    type="messages",
    title="Audi A4 B9 (2017-2024) repair & mod assistant",
    description=DESCRIPTION,
    examples=EXAMPLES,
    cache_examples=False,  # each example is a live API call; don't prebake them
)


# Both flags come from the environment so one file covers every way this runs,
# with no edit between them:
#
#   python src/app.py                                localhost only
#   SHARE=1 python src/app.py                        + a public link, 72 hours
#   SHARE=1 APP_PASSWORD=hunter2 python src/app.py   + a login box in front
#   SHARE=1 gradio src/app.py                        + reload on every save
#
# The share link tunnels to THIS process — the laptop stays the server, so
# nothing is deployed and the link dies when the script does.
SHARE = os.getenv("SHARE") == "1"
AUTH = ("guest", os.getenv("APP_PASSWORD")) if os.getenv("APP_PASSWORD") else None

if __name__ == "__main__" and gr.NO_RELOAD:
    demo.launch(share=SHARE, auth=AUTH)
