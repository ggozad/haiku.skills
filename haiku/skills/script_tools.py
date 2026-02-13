"""Script tool support: AST parsing, tool wrapping, and discovery."""

import ast
import asyncio
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from pydantic_ai import Tool


@dataclass
class ParameterInfo:
    annotation: str
    default: str | None = None
    description: str = ""


@dataclass
class ScriptMetadata:
    name: str
    description: str
    parameters: dict[str, ParameterInfo] = field(default_factory=dict)


def _parse_docstring_args(docstring: str) -> dict[str, str]:
    """Extract parameter descriptions from a Google-style Args section."""
    descriptions: dict[str, str] = {}
    in_args = False
    current_param: str | None = None
    current_desc_lines: list[str] = []

    for line in docstring.splitlines():
        stripped = line.strip()
        if stripped == "Args:":
            in_args = True
            continue
        if in_args:
            # New section (e.g. Returns:, Raises:) ends Args
            if stripped and not stripped.startswith(" ") and stripped.endswith(":"):
                if re.match(r"^[A-Z][a-z]+:$", stripped):
                    break
            param_match = re.match(r"^(\w+)\s*(?:\(.*?\))?\s*:\s*(.*)$", stripped)
            if param_match:
                if current_param:
                    descriptions[current_param] = " ".join(current_desc_lines).strip()
                current_param = param_match.group(1)
                current_desc_lines = [param_match.group(2)]
            elif current_param and stripped:
                current_desc_lines.append(stripped)

    if current_param:
        descriptions[current_param] = " ".join(current_desc_lines).strip()

    return descriptions


def parse_script_metadata(path: Path) -> ScriptMetadata:
    """Extract metadata from a script's main() function via AST."""
    source = path.read_text()
    tree = ast.parse(source)

    # Find main() function
    main_func: ast.FunctionDef | None = None
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            main_func = node
            break

    if main_func is None:
        raise ValueError(f"Script {path} has no main() function")

    # Get description: prefer function docstring, fall back to module docstring
    func_doc = ast.get_docstring(main_func) or ""
    module_doc = ast.get_docstring(tree) or ""
    description = func_doc.split("\n\n")[0].strip() if func_doc else module_doc

    # Parse parameter descriptions from docstring
    param_descriptions = _parse_docstring_args(func_doc) if func_doc else {}

    # Extract parameters
    parameters: dict[str, ParameterInfo] = {}
    args = main_func.args
    num_args = len(args.args)
    num_defaults = len(args.defaults)

    for i, arg in enumerate(args.args):
        annotation = ""
        if arg.annotation:
            annotation = ast.unparse(arg.annotation)

        default = None
        default_index = i - (num_args - num_defaults)
        if default_index >= 0:
            default = ast.literal_eval(args.defaults[default_index])

        parameters[arg.arg] = ParameterInfo(
            annotation=annotation,
            default=default,
            description=param_descriptions.get(arg.arg, ""),
        )

    return ScriptMetadata(
        name=path.stem,
        description=description,
        parameters=parameters,
    )


def create_script_tool(path: Path) -> Tool:
    """Create a pydantic-ai Tool that executes a script via `uv run`."""
    metadata = parse_script_metadata(path)
    script_path = str(path.resolve())

    async def run_script(**kwargs: object) -> str:
        proc = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            script_path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        input_data = json.dumps(kwargs).encode()
        stdout, stderr = await proc.communicate(input=input_data)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Script {path.name} failed (exit {proc.returncode}): "
                f"{stderr.decode().strip()}"
            )
        output = json.loads(stdout.decode())
        return output["result"]

    # Build JSON schema from parsed metadata
    properties: dict[str, dict[str, str]] = {}
    required: list[str] = []
    for name, param in metadata.parameters.items():
        prop: dict[str, str] = {}
        type_map = {
            "str": "string",
            "int": "integer",
            "float": "number",
            "bool": "boolean",
        }
        prop["type"] = type_map.get(param.annotation, "string")
        if param.description:
            prop["description"] = param.description
        properties[name] = prop
        if param.default is None:
            required.append(name)

    json_schema = {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }

    return Tool.from_schema(
        function=run_script,
        name=metadata.name,
        description=metadata.description,
        json_schema=json_schema,
    )


def discover_script_tools(skill_path: Path) -> list[Tool]:
    """Find all script tools in a skill's scripts/ directory."""
    scripts_dir = skill_path / "scripts"
    if not scripts_dir.is_dir():
        return []
    tools: list[Tool] = []
    for script in sorted(scripts_dir.glob("*.py")):
        tools.append(create_script_tool(script))
    return tools
