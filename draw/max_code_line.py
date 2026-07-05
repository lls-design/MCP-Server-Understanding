#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import json
from pathlib import Path


SOURCE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".mjs", ".cjs",
    ".mts", ".cts",
    ".go", ".rs", ".java", ".kt", ".cs", ".c", ".cpp", ".h", ".hpp",
    ".rb", ".php", ".swift", ".scala", ".sh",
}

IGNORE_DIRS = {
    ".git", "node_modules", "dist", "build", "coverage", ".next",
    ".venv", "venv", "myenv", "env", "__pycache__", ".idea", ".vscode", "target",
    ".documcp", ".pytest_cache", ".mypy_cache", "site-packages", ".smithery",
}
NON_IMPLEMENTATION_DIRS = {
    "doc", "docs", "documentation",
    "test", "tests", "__tests__", "spec", "specs",
    "example", "examples", "demo", "demos",
    "fixture", "fixtures", "mock", "mocks",
    "sample", "samples", "template", "templates",
    "benchmark", "benchmarks",
}
FRONTEND_DIRS = {
    "dashboard", "frontend", "web", "webapp", "ui",
    "public", "static", "assets",
}
VENDORED_DIRS = {
    "vendor", "vendors", "third_party", "third-party",
    "external", "fastmcp",
}

# CodeQL database directories are named like "<project>_codeql".
IGNORE_DIR_SUFFIXES = ("_codeql",)

IGNORE_FILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "composer.lock", "poetry.lock", "Cargo.lock",
}


def read_projects(path: Path) -> list[str]:
    return sorted({
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip()
    })


def is_ignored_path(path: Path) -> bool:
    for part in path.parts:
        if part in IGNORE_DIRS:
            return True
        if part.endswith(IGNORE_DIR_SUFFIXES):
            return True
        if "node_modules" in part:
            return True
    return False


def is_non_implementation_path(path: Path) -> bool:
    for part in path.parts:
        normalized = part.lower().strip()
        if normalized in NON_IMPLEMENTATION_DIRS:
            return True
        if normalized.endswith((".test", ".spec")):
            return True
        if normalized.endswith(("-test", "_test", "-tests", "_tests")):
            return True
    name = path.name.lower()
    return (
        ".test." in name
        or ".spec." in name
        or name.startswith("test_")
        or name.endswith("_test.py")
    )


def is_project_excluded_path(project: str, server_dir: Path, path: Path) -> bool:
    rel_parts = path.relative_to(server_dir).parts
    lower_parts = [part.lower().strip() for part in rel_parts]
    project_lower = project.lower()

    if lower_parts:
        top = lower_parts[0]
        if top in VENDORED_DIRS and top not in project_lower:
            return True

    has_mcp_part = any("mcp" in part for part in lower_parts)
    if not has_mcp_part and any(part in FRONTEND_DIRS for part in lower_parts):
        return True

    return False


def is_source_file(path: Path) -> bool:
    if path.name in IGNORE_FILES:
        return False
    if is_ignored_path(path):
        return False
    if is_non_implementation_path(path):
        return False
    return path.suffix.lower() in SOURCE_EXTENSIONS


def is_project_source_file(project: str, server_dir: Path, path: Path) -> bool:
    if is_project_excluded_path(project, server_dir, path):
        return False
    return is_source_file(path)


def iter_call_graph_nodes(call_graph: Path) -> list[dict]:
    data = json.loads(call_graph.read_text(encoding="utf-8", errors="ignore"))
    if isinstance(data, list):
        return [node for node in data if isinstance(node, dict)]
    if isinstance(data, dict):
        if isinstance(data.get("nodes"), list):
            return [node for node in data["nodes"] if isinstance(node, dict)]
        return [node for node in data.values() if isinstance(node, dict)]
    return []


def strip_location_suffix(raw_path: str) -> str:
    parts = raw_path.rsplit(":", 4)
    if len(parts) == 5 and all(part.isdigit() for part in parts[1:]):
        return parts[0]
    return raw_path


def resolve_graph_path(server_dir: Path, raw_path: str) -> Path | None:
    if not raw_path:
        return None
    raw_file = strip_location_suffix(raw_path)
    candidate = Path(raw_file)
    if candidate.is_absolute() and candidate.exists():
        try:
            candidate.relative_to(server_dir)
        except ValueError:
            return None
        return candidate
    candidate = server_dir / raw_file.lstrip("/")
    if candidate.exists():
        return candidate
    return None


def iter_entry_point_files(entry_points: Path) -> list[str]:
    if not entry_points.exists():
        return []
    data = json.loads(entry_points.read_text(encoding="utf-8", errors="ignore"))
    items = data.values() if isinstance(data, dict) else data
    files = []
    for item in items:
        if isinstance(item, dict) and item.get("file"):
            files.append(str(item["file"]))
    return files


def implementation_root_for_file(server_dir: Path, path: Path) -> Path:
    rel = path.relative_to(server_dir)
    parts = rel.parts

    for i, part in enumerate(parts[:-1]):
        if part == "src":
            if i + 1 < len(parts) - 1:
                return server_dir.joinpath(*parts[: i + 2])
            return path

    for i, part in enumerate(parts[:-1]):
        if "mcp" in part.lower():
            return server_dir.joinpath(*parts[: i + 1])

    if len(parts) > 1:
        return server_dir / parts[0]
    return path


def collect_implementation_roots(project: str, server_dir: Path, results_dir: Path) -> list[Path]:
    roots: set[Path] = set()
    call_graph = results_dir / project / "call_graph_labeled.json"
    entry_points = results_dir / project / "entry_points.json"

    for raw_path in iter_entry_point_files(entry_points):
        path = resolve_graph_path(server_dir, raw_path)
        if path is not None and path.is_file() and is_project_source_file(project, server_dir, path):
            roots.add(implementation_root_for_file(server_dir, path))

    if call_graph.exists():
        for node in iter_call_graph_nodes(call_graph):
            path = resolve_graph_path(server_dir, str(node.get("path", "")))
            if path is not None and path.is_file() and is_project_source_file(project, server_dir, path):
                roots.add(implementation_root_for_file(server_dir, path))

    minimal_roots = []
    for root in sorted(roots, key=lambda p: (len(p.parts), str(p))):
        if not any(root.is_relative_to(existing) for existing in minimal_roots):
            minimal_roots.append(root)
    return minimal_roots


def collect_mcp_implementation_files(project: str, server_dir: Path, results_dir: Path) -> list[Path]:
    files: set[Path] = set()
    for root in collect_implementation_roots(project, server_dir, results_dir):
        if root.is_file():
            candidates = [root]
        else:
            candidates = [path for path in root.rglob("*") if path.is_file()]
        for path in candidates:
            if is_project_source_file(project, server_dir, path):
                files.add(path)
    return sorted(files)


def count_project_loc(project: str, server_dir: Path, results_dir: Path) -> tuple[int, int]:
    total_lines = 0
    files = collect_mcp_implementation_files(project, server_dir, results_dir)

    for path in files:
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as f:
                total_lines += sum(1 for _ in f)
        except OSError:
            continue

    return total_lines, len(files)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Count LOC for MCP servers and sort by LOC descending."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("/home/lls/MCP_Analyze"),
        help="Project root directory.",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=0,
        help="Only print top N projects. Use 0 to print all.",
    )
    parser.add_argument(
        "--projects-file",
        type=Path,
        default=None,
        help="Project list file. Defaults to tool_analyzer/success_projects.txt.",
    )
    args = parser.parse_args()

    success_file = args.projects_file or (args.root / "tool_analyzer/success_projects.txt")
    servers_dir = args.root / "Servers"
    results_dir = args.root / "results"

    projects = read_projects(success_file)
    server_index = {p.name: p for p in servers_dir.iterdir() if p.is_dir()}

    rows: list[tuple[int, str, int]] = []
    missing = 0

    for project in projects:
        server_dir = server_index.get(project)
        if server_dir is None:
            missing += 1
            continue

        loc, file_count = count_project_loc(project, server_dir, results_dir)
        if loc > 0:
            rows.append((loc, project, file_count))

    rows.sort(reverse=True)

    print(f"Projects in list: {len(projects)}")
    print(f"Matched projects with LOC: {len(rows)}")
    print(f"Missing server dirs: {missing}")
    print()
    print("rank\tserver\tLOC\tKLOC\tfiles")

    limit = len(rows) if args.top == 0 else min(args.top, len(rows))
    for rank, (loc, project, file_count) in enumerate(rows[:limit], start=1):
        print(f"{rank}\t{project}\t{loc}\t{loc / 1000:.3f}\t{file_count}")


if __name__ == "__main__":
    main()
