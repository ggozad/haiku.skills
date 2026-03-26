from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError
from pydantic_ai.toolsets.function import FunctionToolset

from haiku.skills.models import (
    Skill,
    SkillMetadata,
    SkillSource,
    SkillValidationError,
)


class TestSkillValidationError:
    def test_is_value_error(self):
        err = SkillValidationError("something went wrong", Path("/skills/broken"))
        assert isinstance(err, ValueError)

    def test_stores_path(self):
        p = Path("/skills/broken")
        err = SkillValidationError("bad", p)
        assert err.path is p

    def test_str_returns_message(self):
        err = SkillValidationError("something went wrong", Path("/skills/broken"))
        assert str(err) == "something went wrong"


class TestSkillMetadata:
    def test_minimal(self):
        meta = SkillMetadata(name="my-skill", description="Does things.")
        assert meta.name == "my-skill"
        assert meta.description == "Does things."
        assert meta.license is None
        assert meta.compatibility is None
        assert meta.metadata == {}
        assert meta.allowed_tools == []

    def test_all_fields(self):
        meta = SkillMetadata(
            name="full-skill",
            description="A full skill.",
            license="MIT",
            compatibility="Requires network",
            metadata={"author": "test", "version": "1.0"},
            allowed_tools=["Bash(git:*)", "Read"],
        )
        assert meta.license == "MIT"
        assert meta.compatibility == "Requires network"
        assert meta.metadata == {"author": "test", "version": "1.0"}
        assert meta.allowed_tools == ["Bash(git:*)", "Read"]

    def test_name_validation_uppercase_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="MySkill", description="Bad name.")

    def test_name_validation_leading_hyphen_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="-bad", description="Bad name.")

    def test_name_validation_trailing_hyphen_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="bad-", description="Bad name.")

    def test_name_validation_consecutive_hyphens_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="bad--name", description="Bad name.")

    def test_name_unicode_lowercase_accepted(self):
        meta = SkillMetadata(name="données", description="French skill.")
        assert meta.name == "données"

    def test_name_unicode_uppercase_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="Données", description="Bad name.")

    def test_name_special_characters_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="my_skill!", description="Bad name.")

    def test_name_validation_too_long_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="a" * 65, description="Too long name.")

    def test_name_validation_empty_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="", description="Empty name.")

    def test_description_empty_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="ok", description="")

    def test_description_too_long_rejected(self):
        with pytest.raises(ValidationError):
            SkillMetadata(name="ok", description="x" * 1025)

    def test_allowed_tools_from_string(self):
        meta = SkillMetadata(
            name="test",
            description="Test.",
            allowed_tools="Read Write",  # type: ignore[arg-type]
        )
        assert meta.allowed_tools == ["Read", "Write"]

    def test_allowed_tools_from_empty_string(self):
        meta = SkillMetadata(
            name="test",
            description="Test.",
            allowed_tools="",  # type: ignore[arg-type]
        )
        assert meta.allowed_tools == []

    def test_allowed_tools_from_whitespace_string(self):
        meta = SkillMetadata(
            name="test",
            description="Test.",
            allowed_tools="  ",  # type: ignore[arg-type]
        )
        assert meta.allowed_tools == []

    def test_allowed_tools_from_list(self):
        meta = SkillMetadata(
            name="test", description="Test.", allowed_tools=["Read", "Write"]
        )
        assert meta.allowed_tools == ["Read", "Write"]

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError, match="extra_field"):
            SkillMetadata(
                **{"name": "ok", "description": "Valid.", "extra_field": "unexpected"}  # type: ignore[invalid-argument-type]
            )


class TestSkillSource:
    def test_values(self):
        assert SkillSource.FILESYSTEM.value == "filesystem"
        assert SkillSource.ENTRYPOINT.value == "entrypoint"
        assert SkillSource.MCP.value == "mcp"


class TestSkill:
    def test_minimal(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM)
        assert skill.metadata.name == "test"
        assert skill.source == SkillSource.FILESYSTEM
        assert skill.path is None
        assert skill.instructions is None
        assert skill.tools == []
        assert skill.toolsets == []

    def test_verified_default_false(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM)
        assert skill.verified is False

    def test_verified_settable(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM, verified=True)
        assert skill.verified is True

    def test_with_path_and_instructions(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            path=Path("/some/path"),
            instructions="Do the thing.",
        )
        assert skill.path == Path("/some/path")
        assert skill.instructions == "Do the thing."

    def test_with_tools(self):
        def my_tool(x: int) -> int:
            return x * 2

        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM, tools=[my_tool])
        assert len(skill.tools) == 1
        assert skill.tools[0] is my_tool

    def test_with_toolsets(self):
        toolset = FunctionToolset()
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM, toolsets=[toolset])
        assert len(skill.toolsets) == 1
        assert skill.toolsets[0] is toolset

    def test_tools_and_toolsets_settable(self):
        def tool_a(x: int) -> int:
            return x

        def tool_b(x: int) -> int:
            return x

        toolset = FunctionToolset()
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM)
        skill.tools = [tool_a, tool_b]
        skill.toolsets = [toolset]
        assert len(skill.tools) == 2
        assert len(skill.toolsets) == 1

    def test_resources_default_empty(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM)
        assert skill.resources == []

    def test_resources_settable(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM)
        skill.resources = ["references/REFERENCE.md", "assets/template.txt"]
        assert skill.resources == ["references/REFERENCE.md", "assets/template.txt"]

    def test_tools_and_toolsets_excluded_from_serialization(self):
        def my_tool(x: int) -> int:
            return x * 2

        toolset = FunctionToolset()
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            tools=[my_tool],
            toolsets=[toolset],
        )
        data = skill.model_dump()
        assert "tools" not in data
        assert "toolsets" not in data

    def test_state_type_default_none(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM)
        assert skill.state_type is None
        assert skill.state_namespace is None

    def test_state_type_settable(self):
        class MyState(BaseModel):
            value: int = 0

        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            state_type=MyState,
            state_namespace="ns",
        )
        assert skill.state_type is MyState
        assert skill.state_namespace == "ns"

    def test_state_type_setter(self):
        class MyState(BaseModel):
            value: int = 0

        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM)
        skill.state_type = MyState
        skill.state_namespace = "ns"
        assert skill.state_type is MyState
        assert skill.state_namespace == "ns"

    def test_with_model_instance(self):
        from pydantic_ai.models.test import TestModel

        meta = SkillMetadata(name="test", description="Test skill.")
        model = TestModel()
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM, model=model)
        assert skill.model is model

    def test_state_excluded_from_serialization(self):
        class MyState(BaseModel):
            value: int = 0

        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            state_type=MyState,
            state_namespace="ns",
        )
        data = skill.model_dump()
        assert "state_type" not in data
        assert "state_namespace" not in data

    def test_state_metadata_with_state(self):
        class MyState(BaseModel):
            value: int = 0

        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            state_type=MyState,
            state_namespace="ns",
        )
        result = skill.state_metadata()
        assert result is not None
        assert result.namespace == "ns"
        assert result.type is MyState
        assert result.schema == MyState.model_json_schema()

    def test_state_metadata_without_state(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM)
        assert skill.state_metadata() is None

    def test_state_metadata_partial_type_without_namespace(self):
        class MyState(BaseModel):
            value: int = 0

        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            state_type=MyState,
        )
        assert skill.state_metadata() is None

    def test_state_metadata_partial_namespace_without_type(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.FILESYSTEM,
            state_namespace="ns",
        )
        assert skill.state_metadata() is None


class TestSkillFactory:
    def test_factory_default_none(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM)
        assert skill._factory is None

    def test_factory_stored_via_assignment(self):
        def my_factory() -> Skill:
            return Skill(
                metadata=SkillMetadata(name="test", description="Test."),
                source=SkillSource.ENTRYPOINT,
            )

        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.ENTRYPOINT)
        skill._factory = my_factory
        assert skill._factory is my_factory

    def test_factory_excluded_from_serialization(self):
        def my_factory() -> Skill:
            return Skill(
                metadata=SkillMetadata(name="test", description="Test."),
                source=SkillSource.ENTRYPOINT,
            )

        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.ENTRYPOINT)
        skill._factory = my_factory
        data = skill.model_dump()
        assert "factory" not in data


class TestSkillReconfigure:
    def test_reconfigure_replaces_tools(self):
        def tool_a(x: int) -> int:
            return x

        def tool_b(x: int) -> int:
            return x * 2

        def factory(mode: str = "a") -> Skill:
            tool = tool_a if mode == "a" else tool_b
            return Skill(
                metadata=SkillMetadata(name="test", description="Test."),
                source=SkillSource.ENTRYPOINT,
                tools=[tool],
            )

        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(
            metadata=meta,
            source=SkillSource.ENTRYPOINT,
            tools=[tool_a],
        )
        skill._factory = factory
        assert skill.tools == [tool_a]

        skill.reconfigure(mode="b")
        assert skill.tools == [tool_b]

    def test_reconfigure_replaces_state(self):
        class StateA(BaseModel):
            value: int = 0

        class StateB(BaseModel):
            name: str = ""

        def factory(use_b: bool = False) -> Skill:
            st = StateB if use_b else StateA
            ns = "b" if use_b else "a"
            return Skill(
                metadata=SkillMetadata(name="test", description="Test."),
                source=SkillSource.ENTRYPOINT,
                state_type=st,
                state_namespace=ns,
            )

        skill = Skill(
            metadata=SkillMetadata(name="test", description="Test."),
            source=SkillSource.ENTRYPOINT,
            state_type=StateA,
            state_namespace="a",
        )
        skill._factory = factory
        skill.reconfigure(use_b=True)
        assert skill.state_type is StateB
        assert skill.state_namespace == "b"

    def test_reconfigure_replaces_model(self):
        def factory(use_custom: bool = False) -> Skill:
            m = "custom-model" if use_custom else "default-model"
            return Skill(
                metadata=SkillMetadata(name="test", description="Test."),
                source=SkillSource.ENTRYPOINT,
                model=m,
            )

        skill = Skill(
            metadata=SkillMetadata(name="test", description="Test."),
            source=SkillSource.ENTRYPOINT,
            model="default-model",
        )
        skill._factory = factory
        assert skill.model == "default-model"

        skill.reconfigure(use_custom=True)
        assert skill.model == "custom-model"

    def test_reconfigure_preserves_metadata(self):
        meta = SkillMetadata(name="test", description="Original description.")

        def factory() -> Skill:
            return Skill(
                metadata=SkillMetadata(name="different", description="Different."),
                source=SkillSource.FILESYSTEM,
                instructions="new instructions",
            )

        skill = Skill(
            metadata=meta,
            source=SkillSource.ENTRYPOINT,
            instructions="original instructions",
        )
        skill._factory = factory
        skill.reconfigure()
        assert skill.metadata.name == "test"
        assert skill.metadata.description == "Original description."
        assert skill.source == SkillSource.ENTRYPOINT
        assert skill.instructions == "original instructions"

    def test_reconfigure_without_factory_raises(self):
        meta = SkillMetadata(name="test", description="Test skill.")
        skill = Skill(metadata=meta, source=SkillSource.FILESYSTEM)
        with pytest.raises(RuntimeError, match="no factory"):
            skill.reconfigure()
