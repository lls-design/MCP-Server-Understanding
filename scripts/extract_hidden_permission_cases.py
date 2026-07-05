#!/usr/bin/env python3
import argparse
import json
from pathlib import Path

from permission_transparency import (
    DISCLOSURE_TABLE_FIELDS,
    build_disclosure_table_rows,
    extract_hidden_permission_cases,
    write_csv,
    write_json,
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input-json",
        default="tool_analyzer/permission_transparency_tools.json",
    )
    parser.add_argument(
        "--output-json",
        default="tool_analyzer/permission_transparency_hidden_permission_cases.json",
    )
    parser.add_argument(
        "--table-csv",
        default="tool_analyzer/permission_transparency_table.csv",
    )
    parser.add_argument(
        "--hidden-table-csv",
        default="tool_analyzer/permission_transparency_hidden_table.csv",
    )
    args = parser.parse_args()

    input_path = Path(args.input_json)
    rows = json.loads(input_path.read_text(encoding="utf-8"))
    hidden_cases = extract_hidden_permission_cases(rows)
    table_rows = build_disclosure_table_rows(rows, hidden_only=False)
    hidden_table_rows = build_disclosure_table_rows(rows, hidden_only=True)

    write_json(Path(args.output_json), hidden_cases)
    write_csv(Path(args.table_csv), table_rows, DISCLOSURE_TABLE_FIELDS)
    write_csv(Path(args.hidden_table_csv), hidden_table_rows, DISCLOSURE_TABLE_FIELDS)

    print(json.dumps({
        "input": str(input_path),
        "output": args.output_json,
        "table_csv": args.table_csv,
        "hidden_table_csv": args.hidden_table_csv,
        "tools": len(rows),
        "hidden_permission_cases": len(hidden_cases),
        "table_rows": len(table_rows),
        "hidden_table_rows": len(hidden_table_rows),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
