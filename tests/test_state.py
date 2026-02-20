from ag_ui.core import EventType, StateDeltaEvent
from pydantic import BaseModel
from pydantic_ai.ui import StateHandler

from haiku.skills.state import SkillDeps, SkillRunDeps, compute_state_delta


class SampleState(BaseModel):
    items: list[str] = []
    count: int = 0


class TestSkillRunDeps:
    def test_defaults_none(self):
        deps = SkillRunDeps()
        assert deps.state is None

    def test_with_state(self):
        state = SampleState(items=["a"], count=1)
        deps = SkillRunDeps(state=state)
        assert deps.state is state


class TestSkillDeps:
    def test_defaults_empty_dict(self):
        deps = SkillDeps()
        assert deps.state == {}

    def test_with_state(self):
        state = {"ns": {"items": ["a"], "count": 1}}
        deps = SkillDeps(state=state)
        assert deps.state is state

    def test_satisfies_state_handler(self):
        assert isinstance(SkillDeps(), StateHandler)


class TestComputeStateDelta:
    def test_no_changes_returns_none(self):
        snapshot = {"ns": {"items": [], "count": 0}}
        assert compute_state_delta(snapshot, snapshot) is None

    def test_identical_copies_returns_none(self):
        old = {"ns": {"items": ["a"], "count": 1}}
        new = {"ns": {"items": ["a"], "count": 1}}
        assert compute_state_delta(old, new) is None

    def test_detects_changes(self):
        old = {"ns": {"items": [], "count": 0}}
        new = {"ns": {"items": ["a"], "count": 1}}
        delta = compute_state_delta(old, new)
        assert delta is not None
        assert isinstance(delta, StateDeltaEvent)
        assert delta.type == EventType.STATE_DELTA
        assert len(delta.delta) > 0

    def test_delta_patch_content(self):
        old = {"ns": {"count": 0}}
        new = {"ns": {"count": 5}}
        delta = compute_state_delta(old, new)
        assert delta is not None
        paths = [op["path"] for op in delta.delta]
        assert "/ns/count" in paths

    def test_multiple_namespaces(self):
        old = {"a": {"x": 1}, "b": {"y": 2}}
        new = {"a": {"x": 1}, "b": {"y": 3}}
        delta = compute_state_delta(old, new)
        assert delta is not None
        paths = [op["path"] for op in delta.delta]
        assert "/b/y" in paths

    def test_empty_snapshots_returns_none(self):
        assert compute_state_delta({}, {}) is None
