# /// script
# requires-python = ">=3.13"
# dependencies = ["haiku.rag"]
# ///
"""Search the knowledge base for relevant documents."""

import asyncio
import json
import os
import sys

from haiku.rag.client import HaikuRAG


async def _search(query: str, limit: int = 5) -> str:
    db_path = os.environ.get("HAIKU_RAG_DB_PATH", "")
    if not db_path:
        return "Error: HAIKU_RAG_DB_PATH not set."

    async with HaikuRAG(db_path) as rag:
        results = await rag.search(query, limit=limit)

    if not results:
        return "No results found."

    parts = []
    for i, r in enumerate(results, 1):
        title = r.document_title or "Untitled"
        headings = " > ".join(r.headings) if r.headings else ""
        pages = f"p.{r.page_numbers}" if r.page_numbers else ""
        meta = " | ".join(filter(None, [headings, pages]))
        parts.append(
            f"**{i}. {title}** (score: {r.score:.2f})\n{meta}\n{r.content[:500]}"
        )

    return "\n\n---\n\n".join(parts)


def main(query: str, limit: int = 5) -> str:
    """Search the knowledge base for relevant documents.

    Args:
        query: The search query.
        limit: Maximum number of results to return.
    """
    return asyncio.run(_search(query, limit))


if __name__ == "__main__":
    args = json.loads(sys.stdin.read())
    print(json.dumps({"result": main(**args)}))
