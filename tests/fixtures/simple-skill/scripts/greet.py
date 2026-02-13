"""Generate a greeting message."""

import json
import sys


def main(name: str, greeting: str = "Hello") -> str:
    """Greet someone by name.

    Args:
        name: The person to greet.
        greeting: The greeting to use.
    """
    return f"{greeting}, {name}!"


if __name__ == "__main__":
    args = json.loads(sys.stdin.read())
    result = main(**args)
    json.dump({"result": result}, sys.stdout)
