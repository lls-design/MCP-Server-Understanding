#!/usr/bin/env python3
"""
Run api_analyze.py in batch for all projects under the results directory.
"""
import os
import subprocess
import sys
import argparse
from pathlib import Path

def find_python_executable():
    """Find an available Python interpreter, preferring virtual environments."""
    # Check the virtual environment under the current script directory.
    script_dir = Path(__file__).parent
    venv_python = script_dir / ".venv" / "bin" / "python3"
    if venv_python.exists():
        return str(venv_python)
    
    # Check the virtual environment under the current working directory.
    cwd_venv = Path.cwd() / ".venv" / "bin" / "python3"
    if cwd_venv.exists():
        return str(cwd_venv)
    
    # Check whether the current interpreter is already inside a virtual environment.
    if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        # Already in a virtual environment.
        return sys.executable
    
    # Fall back to the system Python.
    return sys.executable

def get_all_projects(results_dir="results"):
    """Get all project directories under the results directory."""
    results_path = Path(results_dir)
    if not results_path.exists():
        print(f"Error: directory does not exist: {results_dir}")
        return []
    
    projects = []
    for item in results_path.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            # Check whether the required file exists.
            call_graph_path = item / "call_graph.json"
            if call_graph_path.exists():
                projects.append(item.name)
            else:
                print(f"Warning: {item.name} is missing call_graph.json, skipping")
    
    return sorted(projects)

def run_analysis(project_name, results_dir="results", force_rerun=False, cache_path="tool_analyzer/api_cache.json", output_file="call_graph_labeled.json", python_executable=None):
    """Run analysis for a single project."""
    project_path = os.path.join(results_dir, project_name)
    
    if python_executable is None:
        python_executable = find_python_executable()
    
    cmd = [
        python_executable,
        "-u",  # Disable output buffering so logs are shown in real time.
        "api_analyze.py",
        "--project_path", project_path,
        "--cache", cache_path,
        "--output_file", output_file
    ]
    
    if force_rerun:
        cmd.append("--force_rerun")
    
    print(f"\n{'='*80}")
    print(f"Processing project: {project_name}")
    print(f"{'='*80}")
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=False)
        print(f"✓ Project {project_name} processed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Project {project_name} failed: {e}")
        return False
    except KeyboardInterrupt:
        print(f"\nInterrupted by user while processing project: {project_name}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Run api_analyze.py in batch for all projects")
    parser.add_argument("--results_dir", "-r", type=str, default="results", 
                       help="Path to the results directory (default: results)")
    parser.add_argument("--force_rerun", action="store_true",
                       help="Force rerun for all analyses")
    parser.add_argument("--cache", type=str, default="tool_analyzer/api_cache.json",
                       help="API cache file path (default: tool_analyzer/api_cache.json)")
    parser.add_argument("--output_file", type=str, default="call_graph_labeled.json",
                       help="Output file name (default: call_graph_labeled.json)")
    parser.add_argument("--start_from", type=str, default=None,
                       help="Start from the specified project and skip earlier projects")
    parser.add_argument("--start_index", type=int, default=None,
                       help="Start from the specified 1-based index, e.g. 3591 starts from project 3591")
    parser.add_argument("--max_projects", type=int, default=None,
                       help="Maximum number of projects to process")
    
    args = parser.parse_args()
    
    # Find the Python interpreter.
    python_executable = find_python_executable()
    print(f"Using Python interpreter: {python_executable}")
    
    # Validate the Python environment.
    try:
        result = subprocess.run([python_executable, "-c", "import openai; print('Dependency check passed')"], 
                               capture_output=True, text=True, timeout=5)
        if result.returncode != 0:
            print(f"Warning: Python environment may be missing dependencies")
            print(f"Error message: {result.stderr}")
    except Exception as e:
        print(f"Warning: failed to validate Python environment: {e}")
    
    # Get all projects.
    projects = get_all_projects(args.results_dir)
    
    if not projects:
        print("No projects found")
        return
    
    print(f"Found {len(projects)} projects")
    
    # If a start project is specified, skip earlier projects.
    if args.start_from:
        try:
            start_idx = projects.index(args.start_from)
            projects = projects[start_idx:]
            print(f"Starting from project {args.start_from}")
        except ValueError:
            print(f"Warning: project {args.start_from} not found; starting from the first project")
    
    # If a start index is specified, skip earlier projects.
    if args.start_index is not None:
        if args.start_index > 0:
            start_idx = args.start_index - 1  # Convert to 0-based index.
            if start_idx < len(projects):
                projects = projects[start_idx:]
                print(f"Starting from project #{args.start_index} (project name: {projects[0] if projects else 'N/A'})")
            else:
                print(f"Warning: start index {args.start_index} exceeds total projects {len(projects)}; no projects to process")
                projects = []
        else:
            print(f"Warning: start index must be greater than 0, current value: {args.start_index}")
    
    # Limit the number of projects.
    if args.max_projects:
        projects = projects[:args.max_projects]
        print(f"Limiting project count to: {args.max_projects}")
    
    # Statistics.
    total = len(projects)
    success_count = 0
    fail_count = 0
    
    try:
        for idx, project in enumerate(projects, 1):
            print(f"\nProgress: [{idx}/{total}]")
            if run_analysis(project, args.results_dir, args.force_rerun, args.cache, args.output_file, python_executable):
                success_count += 1
            else:
                fail_count += 1
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    
    # Output statistics.
    print(f"\n{'='*80}")
    print(f"Processing completed!")
    print(f"Total: {total} projects")
    print(f"Successful: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"{'='*80}")

if __name__ == "__main__":
    main()
