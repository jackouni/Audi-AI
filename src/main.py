"""CLI loop: while-loop wrapping rag.ask(question, history).

Run from the project root:

    python src/main.py

This file owns everything rag.py refuses to know about — printing, reading
input, commands, and what to do when the API errors. app.py will be the same
twenty lines wrapped in Gradio instead.
"""

import sys

from config import CHAT_MODEL, OPENAI_API_KEY
from memory import ChatHistory
from rag import ask

DIVIDER = "-" * 60

BANNER = f"""\
{DIVIDER}
Audi A4 B9 (2017-2024) repair & mod assistant
{DIVIDER}
Ask about symptoms, repairs, recalls, or modifications.
Commands:  !reset  clear the conversation
           !help   show this list
           exit    quit (or 'quit', or Ctrl-D)
{DIVIDER}"""

EXIT_WORDS = {"exit", "quit"}


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

        if question.lower() in EXIT_WORDS:
            print("Goodbye!")
            break

        if question == "!reset":
            history.clear()
            print("Conversation cleared.")
            continue

        if question == "!help":
            print(BANNER)
            continue

        print("Thinking...", end="\r", flush=True)

        try:
            answer = ask(question, history)
        except KeyboardInterrupt:
            print("Cancelled.        ")
            continue
        except Exception as error:
            # An API hiccup shouldn't end the session — report it and keep the
            # history intact so the next question still has context.
            print(f"Error: {error}        ")
            continue

        print(f"Assistant: {answer}")
        print(DIVIDER)


if __name__ == "__main__":
    if not OPENAI_API_KEY:
        sys.exit("OPENAI_API_KEY is not set. Add it to .env in the project root.")

    print(f"Using {CHAT_MODEL}.")
    run()
