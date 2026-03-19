# /// script
# requires-python = ">=3.13"
# dependencies = ["pydantic-monty"]
# ///
"""Execute Python code safely in a sandboxed environment."""

import os
import sys
import tempfile

from pydantic_monty import Monty


def main(code: str) -> str:
    """Execute Python code and return the output.

    Args:
        code: The Python code to execute.
    """
    old_fd = os.dup(1)
    tmp = tempfile.TemporaryFile(mode="w+")
    os.dup2(tmp.fileno(), 1)
    try:
        result = Monty(code).run()
    finally:
        os.dup2(old_fd, 1)
        os.close(old_fd)

    tmp.seek(0)
    stdout = tmp.read()
    tmp.close()

    parts = [f"```python\n{code}\n```"]
    if stdout:
        parts.append(f"stdout:\n{stdout}")
    if result is not None:
        parts.append(f"result: {result}")
    if not stdout and result is None:
        parts.append("Code executed successfully (no output).")

    return "\n".join(parts)


if __name__ == "__main__":
    print(main(sys.argv[1]))
