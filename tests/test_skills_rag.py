"""Tests for the RAG skill package."""

import tempfile
from pathlib import Path

import pytest

from haiku.skills.models import SkillSource

FIXTURES = Path(__file__).parent / "fixtures"
RAG_DB = FIXTURES / "doclaynet.lancedb"
DOC_ID = "3ad91a7e-61e2-4fb7-9b0b-420e0dcc5420"


@pytest.fixture
def rag_db_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir) / "test.lancedb"


def _get_tool(skill, name):
    """Get a tool function from a skill by name."""
    for tool in skill.tools:
        if callable(tool) and tool.__name__ == name:
            return tool
    raise ValueError(f"Tool {name!r} not found in skill")


class TestRAG:
    def test_create_skill(self):
        from haiku_skills_rag import create_skill

        skill = create_skill()
        assert skill.metadata.name == "rag"
        assert (
            skill.metadata.description
            == "Search, retrieve and analyze documents using RAG (Retrieval Augmented Generation)."
        )
        assert skill.source == SkillSource.ENTRYPOINT
        assert skill.path is not None
        tool_names = {t.__name__ for t in skill.tools if callable(t)}  # type: ignore[union-attr]
        assert tool_names == {
            "search",
            "list_documents",
            "get_document",
            "ask",
            "analyze",
        }

    def test_create_skill_custom_db_path(self, rag_db_path):
        from haiku_skills_rag import create_skill

        skill = create_skill(db_path=rag_db_path)
        assert skill.metadata.name == "rag"
        assert len(skill.tools) == 5

    def test_create_skill_env_db_path(self, monkeypatch, rag_db_path):
        from haiku_skills_rag import create_skill

        monkeypatch.setenv("HAIKU_RAG_DB", str(rag_db_path))
        skill = create_skill(db_path=None)
        assert skill.metadata.name == "rag"

    async def test_list_documents(self):
        from haiku_skills_rag import create_skill

        skill = create_skill(db_path=RAG_DB)
        list_documents = _get_tool(skill, "list_documents")
        results = await list_documents()
        assert len(results) == 1
        assert results[0]["id"] == DOC_ID

    async def test_list_documents_with_filter(self):
        from haiku_skills_rag import create_skill

        skill = create_skill(db_path=RAG_DB)
        list_documents = _get_tool(skill, "list_documents")
        results = await list_documents(filter="title = 'nonexistent'")
        assert len(results) == 0

    async def test_get_document_by_id(self):
        from haiku_skills_rag import create_skill

        skill = create_skill(db_path=RAG_DB)
        get_document = _get_tool(skill, "get_document")
        result = await get_document(query=DOC_ID)
        assert result is not None
        assert result["id"] == DOC_ID
        assert result["content"]

    async def test_get_document_by_title(self):
        from haiku_skills_rag import create_skill

        skill = create_skill(db_path=RAG_DB)
        get_document = _get_tool(skill, "get_document")
        result = await get_document(query="DocLayNet")
        assert result is not None
        assert result["id"] == DOC_ID

    async def test_get_document_by_uri(self):
        from haiku_skills_rag import create_skill

        skill = create_skill(db_path=RAG_DB)
        get_document = _get_tool(skill, "get_document")
        result = await get_document(query="doclaynet.pdf")
        assert result is not None
        assert result["id"] == DOC_ID

    async def test_get_document_not_found(self):
        from haiku_skills_rag import create_skill

        skill = create_skill(db_path=RAG_DB)
        get_document = _get_tool(skill, "get_document")
        result = await get_document(query="nonexistent-document")
        assert result is None

    @pytest.mark.vcr()
    async def test_search(self):
        from haiku_skills_rag import create_skill

        skill = create_skill(db_path=RAG_DB)
        search = _get_tool(skill, "search")
        results = await search(query="document layout")
        assert len(results) > 0

    @pytest.mark.vcr()
    async def test_ask(self, allow_model_requests):
        from haiku_skills_rag import create_skill

        skill = create_skill(db_path=RAG_DB)
        ask = _get_tool(skill, "ask")
        result = await ask(question="What is DocLayNet?")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.vcr()
    async def test_analyze(self, allow_model_requests):
        from haiku_skills_rag import create_skill

        skill = create_skill(db_path=RAG_DB)
        analyze = _get_tool(skill, "analyze")
        result = await analyze(question="How many pages does the document have?")
        assert isinstance(result, str)
        assert "Program:" in result
