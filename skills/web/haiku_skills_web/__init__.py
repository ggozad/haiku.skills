from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import RunContext

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps


class SearchResult(BaseModel):
    title: str
    url: str
    description: str


class PageContent(BaseModel):
    url: str
    content: str


class WebState(BaseModel):
    searches: dict[str, list[SearchResult]] = {}
    pages: dict[str, PageContent] = {}


def search(ctx: RunContext[SkillRunDeps], query: str, count: int = 5) -> str:
    """Search the web using Brave Search.

    Args:
        query: The search query.
        count: Number of results to return.
    """
    from haiku_skills_web.scripts.search import _search

    try:
        raw = _search(query, count)
    except RuntimeError as e:
        return f"Error: {e}"

    results = [SearchResult(**item) for item in raw]
    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, WebState):
        ctx.deps.state.searches[query] = results

    formatted = []
    for r in results:
        formatted.append(f"**{r.title}**\n{r.description}\nURL: {r.url}")
    return "\n\n---\n\n".join(formatted) if formatted else "No results found."


def fetch_page(ctx: RunContext[SkillRunDeps], url: str) -> str:
    """Fetch a web page and extract its main content as text.

    Args:
        url: The URL of the page to fetch.
    """
    from haiku_skills_web.scripts.fetch_page import main

    content = main(url)
    if (
        ctx.deps
        and ctx.deps.state
        and isinstance(ctx.deps.state, WebState)
        and not content.startswith("Error:")
    ):
        ctx.deps.state.pages[url] = PageContent(url=url, content=content)

    return content


def create_skill() -> Skill:
    path = Path(__file__).parent
    metadata, instructions = parse_skill_md(path / "SKILL.md")

    return Skill(
        metadata=metadata,
        source=SkillSource.ENTRYPOINT,
        path=path,
        instructions=instructions,
        tools=[search, fetch_page],
        state_type=WebState,
        state_namespace="web",
    )
