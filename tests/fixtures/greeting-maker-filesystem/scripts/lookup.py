"""Look up an employee by ID."""

if __name__ == "__main__":
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Look up an employee by ID.")
    parser.add_argument(
        "--employee-id", required=True, type=int, help="The employee ID."
    )
    args = parser.parse_args()

    employees = {
        42: {"name": "Alice", "department": "Engineering"},
    }
    emp = employees.get(args.employee_id)
    if emp is None:
        print(f"Error: Employee {args.employee_id} not found")
    else:
        print(json.dumps(emp))
