import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel
from pydantic_ai import RunContext

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps

_client: Any = None
_initialized: bool = False


class Memory(BaseModel):
    name: str
    content: str
    source_description: str


class RecallResult(BaseModel):
    query: str
    facts: list[str]


class MemoryState(BaseModel):
    memories: list[Memory] = []
    recalls: list[RecallResult] = []


def _parse_falkordb_uri(uri: str) -> dict[str, Any]:
    """Parse falkor://[user:password@]host:port into FalkorDriver kwargs."""
    parsed = urlparse(uri)
    result: dict[str, Any] = {
        "host": parsed.hostname or "localhost",
        "port": parsed.port or 6379,
    }
    if parsed.username:
        result["username"] = parsed.username
    if parsed.password:
        result["password"] = parsed.password
    return result


def _build_llm_client() -> Any:
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.environ.get("GRAPHITI_LLM_MODEL", "gpt-oss")
    small_model = os.environ.get("GRAPHITI_SMALL_LLM_MODEL", model)
    return OpenAIGenericClient(
        config=LLMConfig(
            api_key="ollama",
            model=model,
            small_model=small_model,
            base_url=f"{base_url}/v1",
        )
    )


def _build_embedder() -> Any:
    from graphiti_core.embedder.openai import OpenAIEmbedder, OpenAIEmbedderConfig

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    model = os.environ.get("GRAPHITI_EMBEDDING_MODEL", "qwen3-embedding:4b")
    dim = int(os.environ.get("GRAPHITI_EMBEDDING_DIM", "2560"))
    return OpenAIEmbedder(
        config=OpenAIEmbedderConfig(
            api_key="ollama",
            embedding_model=model,
            embedding_dim=dim,
            base_url=f"{base_url}/v1",
        )
    )


def _build_cross_encoder() -> Any:
    from graphiti_core.cross_encoder.openai_reranker_client import OpenAIRerankerClient

    llm_client = _build_llm_client()
    return OpenAIRerankerClient(client=llm_client, config=llm_client.config)


async def _get_client() -> Any:
    from graphiti_core import Graphiti
    from graphiti_core.driver.falkordb_driver import FalkorDriver

    global _client, _initialized
    if _client is None:
        uri = os.environ.get("FALKORDB_URI", "falkor://localhost:6379")
        driver_kwargs = _parse_falkordb_uri(uri)
        driver = FalkorDriver(**driver_kwargs, database=_get_group_id())
        _client = Graphiti(
            graph_driver=driver,
            llm_client=_build_llm_client(),
            embedder=_build_embedder(),
            cross_encoder=_build_cross_encoder(),
        )
    if not _initialized:
        await _client.build_indices_and_constraints()
        _initialized = True
    return _client


def _get_group_id() -> str:
    return os.environ.get("GRAPHITI_GROUP_ID", "default")


async def remember(
    ctx: RunContext[SkillRunDeps],
    content: str,
    name: str = "memory",
    source_description: str = "agent observation",
) -> str:
    """Store a memory as an episode in the knowledge graph.

    Args:
        content: The information to remember.
        name: A label for this memory.
        source_description: Description of where this information came from.
    """
    from graphiti_core.nodes import EpisodeType

    try:
        client = await _get_client()
        await client.add_episode(
            name=name,
            episode_body=content,
            source=EpisodeType.text,
            source_description=source_description,
            reference_time=datetime.now(UTC),
            group_id=_get_group_id(),
        )
    except Exception as e:
        return f"Error: {e}"

    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, MemoryState):
        ctx.deps.state.memories.append(
            Memory(name=name, content=content, source_description=source_description)
        )

    return f"Remembered: {content}"


async def recall(
    ctx: RunContext[SkillRunDeps],
    query: str,
    num_results: int = 10,
) -> str:
    """Search the knowledge graph for relevant memories.

    Args:
        query: The search query.
        num_results: Maximum number of results to return.
    """
    try:
        client = await _get_client()
        edges = await client.search(
            query=query,
            group_ids=[_get_group_id()],
            num_results=num_results,
        )
    except Exception as e:
        return f"Error: {e}"

    facts = [edge.fact for edge in edges]

    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, MemoryState):
        ctx.deps.state.recalls.append(RecallResult(query=query, facts=facts))

    if not facts:
        return f"No memories found for: {query}"

    formatted = [f"- {fact}" for fact in facts]
    return "\n".join(formatted)


async def forget(
    ctx: RunContext[SkillRunDeps],
    query: str,
    num_results: int = 10,
) -> str:
    """Remove matching facts from the knowledge graph.

    Args:
        query: Search query to find memories to remove.
        num_results: Maximum number of memories to remove.
    """
    try:
        client = await _get_client()
        edges = await client.search(
            query=query,
            group_ids=[_get_group_id()],
            num_results=num_results,
        )
    except Exception as e:
        return f"Error: {e}"

    if not edges:
        return f"No matching memories found for: {query}"

    deleted_facts = []
    for edge in edges:
        await edge.delete(client.driver)
        deleted_facts.append(edge.fact)

    formatted = [f"- {fact}" for fact in deleted_facts]
    return "Deleted memories:\n" + "\n".join(formatted)


def create_skill() -> Skill:
    skill_dir = Path(__file__).parent / "graphiti-memory"
    metadata, instructions = parse_skill_md(skill_dir / "SKILL.md")

    return Skill(
        metadata=metadata,
        source=SkillSource.ENTRYPOINT,
        path=skill_dir,
        instructions=instructions,
        tools=[remember, recall, forget],
        state_type=MemoryState,
        state_namespace="graphiti-memory",
    )
