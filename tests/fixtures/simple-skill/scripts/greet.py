"""Generate a greeting message."""


def main(name: str, greeting: str = "Hello") -> str:
    """Greet someone by name.

    Args:
        name: The person to greet.
        greeting: The greeting to use.
    """
    return f"{greeting}, {name}!"


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate a greeting message.")
    parser.add_argument("--name", required=True, help="The person to greet.")
    parser.add_argument("--greeting", default="Hello", help="The greeting to use.")
    args = parser.parse_args()
    print(main(args.name, args.greeting))
