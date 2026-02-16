import os
from pathlib import Path
from typing import Any

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md


def create_skill(
    db_path: Path | None = None,
    config: Any = None,
) -> Skill:
    """Create a RAG skill with closure-based tools.

    Args:
        db_path: Path to the LanceDB database. Resolved from:
            1. This argument
            2. HAIKU_RAG_DB environment variable
            3. haiku.rag default (config.storage.data_dir / "haiku.rag.lancedb")
        config: haiku.rag AppConfig instance. If None, uses get_config().
    """
    from haiku.rag.config import get_config

    if config is None:
        config = get_config()

    if db_path is None:
        env_db = os.environ.get("HAIKU_RAG_DB")
        if env_db:
            db_path = Path(env_db).expanduser()
        else:
            db_path = config.storage.data_dir / "haiku.rag.lancedb"

    path = Path(__file__).parent
    metadata, _ = parse_skill_md(path / "SKILL.md")

    async def search(query: str, limit: int | None = None) -> list[dict[str, Any]]:
        """Search the knowledge base using hybrid search (vector + full-text).

        Args:
            query: The search query.
            limit: Maximum number of results.
        """
        from haiku.rag.client import HaikuRAG

        async with HaikuRAG(db_path, config=config, read_only=True) as rag:
            results = await rag.search(query, limit=limit)
            return [r.model_dump() for r in results]

    async def list_documents(
        limit: int | None = None,
        offset: int | None = None,
        filter: str | None = None,
    ) -> list[dict[str, Any]]:
        """List documents in the knowledge base with optional pagination and filtering.

        Args:
            limit: Maximum number of documents to return.
            offset: Number of documents to skip.
            filter: Optional SQL WHERE clause to filter documents.
        """
        from haiku.rag.client import HaikuRAG

        async with HaikuRAG(db_path, config=config, read_only=True) as rag:
            documents = await rag.list_documents(limit, offset, filter)
            return [
                {
                    "id": doc.id,
                    "title": doc.title,
                    "uri": doc.uri,
                    "metadata": doc.metadata,
                    "created_at": str(doc.created_at),
                    "updated_at": str(doc.updated_at),
                }
                for doc in documents
            ]

    async def get_document(query: str) -> dict[str, Any] | None:
        """Retrieve a document by ID, title, or URI.

        Tries exact ID match first, then partial URI match, then partial title match.

        Args:
            query: Document ID, title, or URI to look up.
        """
        from haiku.rag.client import HaikuRAG

        async with HaikuRAG(db_path, config=config, read_only=True) as rag:
            document = await rag.get_document_by_id(query)
            if document is None:
                escaped = query.replace("'", "''")
                docs = await rag.list_documents(
                    limit=1,
                    filter=f"LOWER(uri) LIKE LOWER('%{escaped}%')",
                )
                if not docs:
                    docs = await rag.list_documents(
                        limit=1,
                        filter=f"LOWER(title) LIKE LOWER('%{escaped}%')",
                    )
                if docs and docs[0].id:
                    document = await rag.get_document_by_id(docs[0].id)
            if document is None:
                return None
            return {
                "id": document.id,
                "content": document.content,
                "title": document.title,
                "uri": document.uri,
                "metadata": document.metadata,
                "created_at": str(document.created_at),
                "updated_at": str(document.updated_at),
            }

    async def ask(question: str) -> str:
        """Ask a question and get an answer with citations from the knowledge base.

        Args:
            question: The question to ask.
        """
        from haiku.rag.client import HaikuRAG
        from haiku.rag.utils import format_citations

        async with HaikuRAG(db_path, config=config, read_only=True) as rag:
            answer, citations = await rag.ask(question)
            if citations:
                answer += "\n\n" + format_citations(citations)
            return answer

    async def analyze(
        question: str,
        document: str | None = None,
        filter: str | None = None,
    ) -> str:
        """Answer complex analytical questions using code execution.

        Use this for questions requiring computation, aggregation, or
        data traversal across documents.

        Args:
            question: The question to answer.
            document: Optional document ID or title to pre-load for analysis.
            filter: Optional SQL WHERE clause to filter documents.
        """
        from haiku.rag.client import HaikuRAG

        async with HaikuRAG(db_path, config=config, read_only=True) as rag:
            documents = [document] if document else None
            result = await rag.rlm(question, documents=documents, filter=filter)
            output = result.answer
            if result.program:
                output += f"\n\nProgram:\n{result.program}"
            return output

    return Skill(
        metadata=metadata,
        source=SkillSource.ENTRYPOINT,
        path=path,
        tools=[search, list_documents, get_document, ask, analyze],
    )
