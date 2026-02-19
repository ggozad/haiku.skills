import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic_ai import RunContext

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps


class RAGSearchResult(BaseModel):
    chunk_id: str
    document_title: str
    content: str
    score: float


class RAGDocument(BaseModel):
    id: str
    title: str
    uri: str | None


class RAGAnswer(BaseModel):
    question: str
    answer: str


class RAGState(BaseModel):
    searches: dict[str, list[RAGSearchResult]] = {}
    documents: list[RAGDocument] = []
    answers: list[RAGAnswer] = []


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
    metadata, instructions = parse_skill_md(path / "SKILL.md")

    async def search(
        ctx: RunContext[SkillRunDeps], query: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        """Search the knowledge base using hybrid search (vector + full-text).

        Args:
            query: The search query.
            limit: Maximum number of results.
        """
        from haiku.rag.client import HaikuRAG

        async with HaikuRAG(db_path, config=config, read_only=True) as rag:
            results = await rag.search(query, limit=limit)
            result_dicts = [r.model_dump() for r in results]

        if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, RAGState):
            rag_results = []
            for r in result_dicts:
                rag_results.append(
                    RAGSearchResult(
                        chunk_id=str(r.get("chunk_id") or ""),
                        document_title=str(r.get("document_title") or ""),
                        content=str(r.get("content") or ""),
                        score=float(r.get("score", 0.0)),
                    )
                )
            ctx.deps.state.searches[query] = rag_results

        return result_dicts

    async def list_documents(
        ctx: RunContext[SkillRunDeps],
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
            result = [
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

        if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, RAGState):
            for doc_dict in result:
                doc = RAGDocument(
                    id=str(doc_dict["id"]),
                    title=str(doc_dict["title"]),
                    uri=doc_dict.get("uri"),
                )
                if not any(d.id == doc.id for d in ctx.deps.state.documents):
                    ctx.deps.state.documents.append(doc)

        return result

    async def get_document(
        ctx: RunContext[SkillRunDeps], query: str
    ) -> dict[str, Any] | None:
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
            result = {
                "id": document.id,
                "content": document.content,
                "title": document.title,
                "uri": document.uri,
                "metadata": document.metadata,
                "created_at": str(document.created_at),
                "updated_at": str(document.updated_at),
            }

        if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, RAGState):
            doc = RAGDocument(
                id=str(result["id"]),
                title=str(result["title"]),
                uri=result.get("uri"),
            )
            if not any(d.id == doc.id for d in ctx.deps.state.documents):
                ctx.deps.state.documents.append(doc)

        return result

    async def ask(ctx: RunContext[SkillRunDeps], question: str) -> str:
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

        if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, RAGState):
            ctx.deps.state.answers.append(RAGAnswer(question=question, answer=answer))

        return answer

    async def analyze(
        ctx: RunContext[SkillRunDeps],
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

        if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, RAGState):
            ctx.deps.state.answers.append(RAGAnswer(question=question, answer=output))

        return output

    return Skill(
        metadata=metadata,
        source=SkillSource.ENTRYPOINT,
        path=path,
        instructions=instructions,
        tools=[search, list_documents, get_document, ask, analyze],
        state_type=RAGState,
        state_namespace="rag",
    )
