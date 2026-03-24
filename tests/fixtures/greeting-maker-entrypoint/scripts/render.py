"""Render a template by substituting {key} placeholders."""

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Render a template string.")
    parser.add_argument("--template", required=True, help="The template string.")
    parser.add_argument("--name", required=True, help="The name value.")
    parser.add_argument("--department", required=True, help="The department value.")
    args = parser.parse_args()
    print(args.template.format(name=args.name, department=args.department))
