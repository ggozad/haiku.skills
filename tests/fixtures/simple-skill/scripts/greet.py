"""Generate a greeting message."""

import sys


def main(name: str, greeting: str = "Hello") -> str:
    """Greet someone by name.

    Args:
        name: The person to greet.
        greeting: The greeting to use.
    """
    return f"{greeting}, {name}!"


if __name__ == "__main__":
    name = sys.argv[1]
    greeting = sys.argv[2] if len(sys.argv) > 2 else "Hello"
    print(main(name, greeting))
