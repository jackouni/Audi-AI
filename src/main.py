"""CLI loop: while-loop wrapping rag.ask(question, history).

Run from the project root:

    python src/main.py

This file owns everything rag.py refuses to know about — printing, reading
input, commands, and what to do when the API errors. app.py will be the same
twenty lines wrapped in Gradio instead.
"""

from memory import ChatHistory
from rag import ask

DIVIDER = "-" * 60

BANNER = f"""\
{DIVIDER}
Audi A4 B9 (2017-2024) repair & mod assistant
{DIVIDER}
Ask about symptoms, repairs, recalls, or modifications.
Commands:  !reset  clear the conversation
           exit    quit (or 'quit', or Ctrl-D)
{DIVIDER}"""


def run() -> None:
    history = ChatHistory()
    print(BANNER)

    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            # Ctrl-D / Ctrl-C at the prompt is a normal way to leave.
            print("\nGoodbye!")
            break

        if not question:
            continue

        if question.lower() in ("exit", "quit"):
            print("Goodbye!")
            break

        if question == "!reset":
            history.clear()
            print("Conversation cleared.")
            continue

        print("Thinking...")

        try:
            answer = ask(question, history)
        except KeyboardInterrupt:
            print("Cancelled.")
            continue
        except Exception as error:
            # An API hiccup shouldn't end the session...
            # log it and keep history intact so the next question still has context.
            print(f"Error: {error}")
            continue

        print(f"Assistant: {answer}")
        print(DIVIDER)


if __name__ == "__main__":
    run()
