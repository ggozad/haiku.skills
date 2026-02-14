# /// script
# requires-python = ">=3.13"
# dependencies = ["haiku.rag"]
# ///
"""Answer questions using the knowledge base with citations."""

import asyncio
import json
import os
import sys

from haiku.rag.client import HaikuRAG


async def _ask(question: str) -> str:
    db_path = os.environ.get("HAIKU_RAG_DB_PATH", "")
    if not db_path:
        return "Error: HAIKU_RAG_DB_PATH not set."

    async with HaikuRAG(db_path) as rag:
        answer, citations = await rag.ask(question)

    parts = [answer]
    if citations:
        parts.append("\n**Sources:**")
        for cite in citations:
            title = cite.document_title or "Untitled"
            pages = f"p.{cite.page_numbers}" if cite.page_numbers else ""
            meta = " | ".join(filter(None, [title, pages]))
            parts.append(f"- [{meta}] {cite.content[:200]}")

    return "\n".join(parts)


def main(question: str) -> str:
    """Answer a question using the knowledge base with citations.

    Args:
        question: The question to answer.
    """
    return asyncio.run(_ask(question))


if __name__ == "__main__":
    args = json.loads(sys.stdin.read())
    print(json.dumps({"result": main(**args)}))
