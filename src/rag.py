"""ask(question, history) -> str. No print, no input, no Gradio import — main.py and app.py are thin wrappers around this.

The runtime chain, in order:

    1. retrieve context for the question (retrieval.py — not wired up yet)
    2. assemble the prompt: system instructions + chunks + history + question
    3. send it, get an answer back
    4. append the turn — and only the turn — to history

Step 2 is where the "retrieved chunks stay out of permanent history" rule is
enforced: the system prompt and the context block are built fresh into the
request list on every call and thrown away afterwards. `history` only ever holds
plain user/assistant messages.
"""

from openai import OpenAI

from config import CHAT_MODEL, OPENAI_API_KEY
from memory import ChatHistory, Message

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """\
You are a knowledgeable Audi A4 (B9, 2017-2024) repair and modification \
assistant. You help owners diagnose problems, understand repairs, and evaluate \
modifications.

How to answer:
- When reference excerpts are provided, ground your answer in them and say what \
they show. Cite the source inline, e.g. "(NHTSA complaint)" or "(r/Audi thread)".
- If the excerpts don't cover the question, say so plainly before falling back \
to general knowledge, and mark that part as general knowledge rather than \
something from the sources.
- Never blend generations. The B8/B8.5 (2009-2016) and B9 (2017+) A4 are \
different cars; if a source is about a different generation or engine than the \
one asked about, flag it instead of quietly applying it.
- Be direct and practical. Owner-level language, not service-manual prose. Give \
the likely cause first, then how to confirm it.
- Safety-critical work (brakes, airbags, suspension, fuel) gets an explicit note \
to verify against factory torque specs and procedures.
"""

CONTEXT_TEMPLATE = """\
Reference excerpts retrieved for this question. They are the only sources you \
have; they may be partial or only loosely relevant, so use judgment.

{context}
"""


def retrieve_context(question: str, history: ChatHistory) -> str:
    """Fetch reference chunks for this question. Stubbed until retrieval.py lands.

    Returning "" makes ask() run as a plain chatbot — same prompt assembly, same
    memory, just no context block — so the conversation loop is testable before
    the database is. Wiring retrieval in is this function's body:

        from retrieval import search
        chunks = search(question, history)
        return "\\n\\n---\\n\\n".join(chunk["chunk_text"] for chunk in chunks)

    Nothing else in this file changes.
    """
    return ""


def build_input(question: str, history: ChatHistory, context: str) -> list[dict]:
    """System prompt + (context) + history + question, as the API wants it.

    Order matters: instructions first, then the fresh context, then the running
    conversation, then the new question last so it's the thing being answered.
    """
    messages = [Message("developer", SYSTEM_PROMPT).to_dict()]

    if context:
        messages.append(Message("developer", CONTEXT_TEMPLATE.format(context=context)).to_dict())

    messages.extend(history.to_list())
    messages.append(Message("user", question).to_dict())

    return messages


def ask(question: str, history: ChatHistory) -> str:
    """Answer a question in the context of the conversation so far.

    The one function every interface calls. Appends the completed turn to
    `history` as a side effect — and only after the API call succeeds, so a
    failed request doesn't leave a dangling user message with no answer under it.
    """
    context = retrieve_context(question, history)

    response = client.responses.create(
        model=CHAT_MODEL,
        input=build_input(question, history, context),
    )
    answer = response.output_text

    history.add_turn(question, answer)

    return answer
