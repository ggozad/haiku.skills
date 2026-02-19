from pathlib import Path

from pydantic import BaseModel
from pydantic_ai import RunContext

from haiku.skills.models import Skill, SkillSource
from haiku.skills.parser import parse_skill_md
from haiku.skills.state import SkillRunDeps


class GeneratedImage(BaseModel):
    prompt: str
    path: str
    width: int
    height: int


class ImageState(BaseModel):
    images: list[GeneratedImage] = []


def generate_image(
    ctx: RunContext[SkillRunDeps],
    prompt: str,
    width: int = 1024,
    height: int = 1024,
) -> str:
    """Generate an image from a text prompt.

    Args:
        prompt: The text description of the image to generate.
        width: Image width in pixels.
        height: Image height in pixels.
    """
    from haiku_skills_image_generation.scripts.generate_image import main

    result = main(prompt, width=width, height=height)

    if ctx.deps and ctx.deps.state and isinstance(ctx.deps.state, ImageState):
        # Parse the markdown image: ![prompt](path)
        if result.startswith("![") and result.endswith(")"):
            paren_start = result.rfind("(")
            image_path = result[paren_start + 1 : -1]
            ctx.deps.state.images.append(
                GeneratedImage(
                    prompt=prompt,
                    path=image_path,
                    width=width,
                    height=height,
                )
            )

    return result


def create_skill() -> Skill:
    skill_dir = Path(__file__).parent / "image-generation"
    metadata, instructions = parse_skill_md(skill_dir / "SKILL.md")

    return Skill(
        metadata=metadata,
        source=SkillSource.ENTRYPOINT,
        path=skill_dir,
        instructions=instructions,
        tools=[generate_image],
        state_type=ImageState,
        state_namespace="image-generation",
    )
