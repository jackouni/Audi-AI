"""ask(question, history) -> str. No print, no input, no Gradio import — main.py and app.py are thin wrappers around this.

The runtime chain, in order:

    1. retrieve context for the question (retrieval.py: condense -> embed -> search)
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
from retrieval import search

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

# An empty result is information, not a failure — it means nothing in the corpus
# cleared the similarity threshold. Saying so explicitly is what stops the model
# from inventing a citation for an answer it pulled from general knowledge.
NO_CONTEXT = """\
The search of the reference corpus returned nothing above the relevance \
threshold for this question. Answer from general knowledge, and say up front \
that the sources don't cover it.
"""

EXCERPT_TEMPLATE = """\
[{number}] {title} ({source_type}, similarity {similarity:.2f}){url}
{text}"""


def format_chunks(chunks: list[dict]) -> str:
    """Render retrieved chunks as a numbered, attributed block.

    The chunk text already carries a `[model · year · category · source_type]`
    header — ingest.py's `decorate()` prefixes it before embedding. The header
    added here is for the model's benefit at answer time: a title and source type
    to cite, and a similarity score so a 0.31 match reads as weaker evidence than
    a 0.72 one.
    """
    return "\n\n---\n\n".join(
        EXCERPT_TEMPLATE.format(
            number=number,
            title=chunk.get("title") or chunk["source_file"],
            source_type=chunk.get("source_type") or "unknown source",
            similarity=chunk["similarity"],
            url=f"\n{chunk['url']}" if chunk.get("url") else "",
            text=chunk["chunk_text"],
        )
        for number, chunk in enumerate(chunks, start=1)
    )


def retrieve_context(question: str, history: ChatHistory) -> str:
    """Fetch reference chunks for this question and build the context message.

    Everything interesting happens in retrieval.py — condensing the follow-up
    into a standalone query, embedding it, running the similarity search. This
    function is just the seam where chunk dicts become prompt text.

    Returns the finished developer message, not raw excerpts, because the two
    outcomes need different framing: a hit list is introduced as "your sources",
    an empty result as "the search found nothing".
    """
    chunks = search(question, history)

    if not chunks:
        return NO_CONTEXT

    return CONTEXT_TEMPLATE.format(context=format_chunks(chunks))


def build_input(question: str, history: ChatHistory, context: str) -> list[dict]:
    """System prompt + (context) + history + question, as the API wants it.

    Order matters: instructions first, then the fresh context, then the running
    conversation, then the new question last so it's the thing being answered.
    """
    messages = [Message("developer", SYSTEM_PROMPT).to_dict()]

    if context:
        messages.append(Message("developer", context).to_dict())

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
