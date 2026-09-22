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

from config import CHAT_MODEL, OPENAI_API_KEY, STRONG_MATCH_THRESHOLD
from memory import ChatHistory
from retrieval import search

client = OpenAI(api_key=OPENAI_API_KEY)

SYSTEM_PROMPT = """\
You are a knowledgeable Audi A4 (B9, 2017-2024) repair and modification \
assistant. You help owners diagnose problems, understand repairs, and evaluate \
modifications.

The one hard rule: a number you cannot point to in an excerpt should not be confidently \
commented on, you can take a best-guess but mention that you aren't certain - it's okay to \
say "I don't know, but here's what I can estimate" - soften with "verify against the manual" afterwards. Owners torque wheels to \
the number you give them, and recalling one from memory is the single way this \
assistant can get someone hurt.

So when the sources don't have the figure, the answer is the sentence "I don't \
have that spec in my sources" plus where to get it — Erwin, the owner's manual, \
a dealer parts desk. Then stop. Describing the procedure around the missing \
number is welcome; supplying the number is not.

How to answer:
- When reference excerpts are provided, ground your answer in them and say what \
they show. Cite the source inline, e.g. "(NHTSA complaint)" or "(r/Audi thread)".
- Attribute facts to the right car. A single thread holds several owners with \
different model years, mileages and repair bills; keep them apart and say whose \
is whose rather than merging them into one story. If the excerpts don't state \
the figure for the car actually being asked about, say that instead of \
substituting the nearest one you can see.
- If the excerpts don't cover the question, open by saying so plainly, then \
answer from general knowledge clearly marked as general knowledge.
- Never blend generations. The B8/B8.5 (2009-2016) and B9 (2017+) A4 are \
different cars; if a source is about a different generation or engine than the \
one asked about, flag it instead of quietly applying it. This corpus is B9 only, \
so a question about another generation has no sources behind it by definition.
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

# Every document in the corpus is Audi A4 prose, so a car-shaped question the
# corpus can't answer still pulls five chunks of plausible-looking neighbours
# rather than pulling nothing. An empty result is a clear signal; this band is
# the one that quietly produced invented torque specs, so it gets said out loud.
WEAK_CONTEXT_TEMPLATE = """\
The search returned only weak matches for this question. The excerpts below \
scored low enough that the corpus most likely does not cover what was asked — \
they are probably neighbouring topics, not the answer.

Open your reply by saying the sources don't cover this question. Then answer \
from general knowledge, marked as such, and withhold any specific figure you \
cannot point to in an excerpt.

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
            title=chunk["title"] or chunk["source_file"],
            source_type=chunk["source_type"] or "unknown source",
            similarity=chunk["similarity"],
            url=f"\n{chunk['url']}" if chunk["url"] else "",
            text=chunk["chunk_text"],
        )
        for number, chunk in enumerate(chunks, start=1)
    )


def retrieve_context(question: str, history: ChatHistory) -> str:
    """Fetch reference chunks for this question and build the context message.

    Everything interesting happens in retrieval.py — condensing the follow-up
    into a standalone query, embedding it, running the similarity search. This
    function is just the seam where chunk dicts become prompt text.

    Returns the finished developer message, not raw excerpts, because the three
    outcomes need different framing: a solid hit list is introduced as "your
    sources", a weak one as "probably not the answer", an empty result as "the
    search found nothing".
    """
    chunks = search(question, history)

    if not chunks:
        return NO_CONTEXT

    template = (
        CONTEXT_TEMPLATE
        if chunks[0]["similarity"] >= STRONG_MATCH_THRESHOLD
        else WEAK_CONTEXT_TEMPLATE
    )
    return template.format(context=format_chunks(chunks))


def build_input(question: str, history: ChatHistory, context: str) -> list[dict]:
    """System prompt + (context) + history + question, as the API wants it.

    Order matters: instructions first, then the fresh context, then the running
    conversation, then the new question last so it's the thing being answered.
    """
    return [
        {"role": "developer", "content": SYSTEM_PROMPT},
        {"role": "developer", "content": context},
        *history.to_list(),
        {"role": "user", "content": question},
    ]


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
