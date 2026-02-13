from pathlib import Path

import pytest

from haiku.skills.script_tools import (
    create_script_tool,
    discover_script_tools,
    parse_script_metadata,
)

FIXTURES = Path(__file__).parent / "fixtures"
GREET_SCRIPT = FIXTURES / "simple-skill" / "scripts" / "greet.py"


class TestParseScriptMetadata:
    def test_extracts_name_from_filename(self):
        meta = parse_script_metadata(GREET_SCRIPT)
        assert meta.name == "greet"

    def test_extracts_docstring(self):
        meta = parse_script_metadata(GREET_SCRIPT)
        assert meta.description == "Greet someone by name."

    def test_extracts_parameters(self):
        meta = parse_script_metadata(GREET_SCRIPT)
        assert "name" in meta.parameters
        assert meta.parameters["name"].annotation == "str"
        assert meta.parameters["name"].default is None
        assert meta.parameters["name"].description == "The person to greet."

    def test_extracts_default_values(self):
        meta = parse_script_metadata(GREET_SCRIPT)
        assert "greeting" in meta.parameters
        assert meta.parameters["greeting"].default == "Hello"
        assert meta.parameters["greeting"].description == "The greeting to use."

    def test_falls_back_to_module_docstring(self, tmp_path: Path):
        script = tmp_path / "tool.py"
        script.write_text(
            '"""Module doc."""\n'
            "import json, sys\n"
            "def main(x: int) -> str:\n"
            "    return str(x)\n"
            'if __name__ == "__main__":\n'
            "    args = json.loads(sys.stdin.read())\n"
            '    json.dump({"result": main(**args)}, sys.stdout)\n'
        )
        meta = parse_script_metadata(script)
        assert meta.description == "Module doc."

    def test_no_docstring(self, tmp_path: Path):
        script = tmp_path / "tool.py"
        script.write_text(
            "import json, sys\n"
            "def main(x: int) -> str:\n"
            "    return str(x)\n"
            'if __name__ == "__main__":\n'
            "    args = json.loads(sys.stdin.read())\n"
            '    json.dump({"result": main(**args)}, sys.stdout)\n'
        )
        meta = parse_script_metadata(script)
        assert meta.description == ""

    def test_multiline_param_description(self, tmp_path: Path):
        script = tmp_path / "tool.py"
        script.write_text(
            "import json, sys\n"
            "def main(data: str) -> str:\n"
            '    """Process data.\n'
            "\n"
            "    Args:\n"
            "        data: The input data\n"
            "            that spans multiple lines.\n"
            "\n"
            "    Returns:\n"
            "        The processed result.\n"
            '    """\n'
            "    return data\n"
            'if __name__ == "__main__":\n'
            "    args = json.loads(sys.stdin.read())\n"
            '    json.dump({"result": main(**args)}, sys.stdout)\n'
        )
        meta = parse_script_metadata(script)
        assert meta.parameters["data"].description == (
            "The input data that spans multiple lines."
        )

    def test_missing_main_raises(self, tmp_path: Path):
        script = tmp_path / "no_main.py"
        script.write_text("x = 1\n")
        with pytest.raises(ValueError, match="main"):
            parse_script_metadata(script)


class TestCreateScriptTool:
    def test_creates_tool_with_correct_name(self):
        tool = create_script_tool(GREET_SCRIPT)
        assert tool.name == "greet"

    def test_creates_tool_with_description(self):
        tool = create_script_tool(GREET_SCRIPT)
        assert tool.description is not None
        assert "Greet someone" in tool.description

    async def test_executes_script(self):
        tool = create_script_tool(GREET_SCRIPT)
        result = await tool.function(name="World")
        assert result == "Hello, World!"

    async def test_executes_script_with_optional_arg(self):
        tool = create_script_tool(GREET_SCRIPT)
        result = await tool.function(name="World", greeting="Hi")
        assert result == "Hi, World!"

    async def test_script_failure_raises(self, tmp_path: Path):
        script = tmp_path / "bad.py"
        script.write_text(
            "import json, sys\n"
            "def main(x: int) -> str:\n"
            '    """Fail."""\n'
            "    raise ValueError('boom')\n"
            'if __name__ == "__main__":\n'
            "    args = json.loads(sys.stdin.read())\n"
            '    json.dump({"result": main(**args)}, sys.stdout)\n'
        )
        tool = create_script_tool(script)
        with pytest.raises(RuntimeError, match="bad.py failed"):
            await tool.function(x=1)


class TestDiscoverScriptTools:
    def test_discovers_scripts_in_directory(self):
        skill_path = FIXTURES / "simple-skill"
        tools = discover_script_tools(skill_path)
        assert len(tools) == 1
        assert tools[0].name == "greet"

    def test_returns_empty_for_no_scripts_dir(self):
        skill_path = FIXTURES / "skill-with-refs"
        tools = discover_script_tools(skill_path)
        assert tools == []

    def test_returns_empty_for_nonexistent_path(self, tmp_path: Path):
        tools = discover_script_tools(tmp_path / "nonexistent")
        assert tools == []
