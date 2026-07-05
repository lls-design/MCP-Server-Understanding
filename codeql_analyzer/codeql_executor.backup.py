import code
import shutil
import subprocess
import os
import sys
import logging
from pathlib import Path
from typing import Dict, Optional
import json
import pydot

logger = logging.getLogger("call_graph_analyze")

def check_codeql_installation(codeql_path: str) -> bool:
    """
    Check if CodeQL CLI is properly installed and accessible.
    
    Args:
        codeql_path: Path to the CodeQL CLI executable
        
    Returns:
        bool: True if CodeQL is available, False otherwise
    """
    try:
        result = subprocess.run(
            [codeql_path, "--version"],
            capture_output=True,
            text=True,
            check=True
        )
        logger.info(f"CodeQL version: {result.stdout.strip()}")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        logger.error(f"CodeQL CLI not found or not working: {e.stderr}")
        return False


def detect_project_type(project_path: str) -> Optional[str]:
    """
    Detect if the project is Python or TypeScript based on common indicators.
    
    Args:
        project_path: Path to the project root
        
    Returns:
        str: 'python', 'typescript', or None if undetermined
    """
    project_path_obj = Path(project_path)
    
    # Check for Python indicators
    python_indicators = [
        'requirements.txt', 'setup.py', 'pyproject.toml', 
        'Pipfile', 'poetry.lock', '__init__.py'
    ]
    
    # Check for TypeScript indicators
    typescript_indicators = [
        'package.json', 'tsconfig.json', 'yarn.lock', 
        'package-lock.json', 'angular.json', 'vue.config.js'
    ]
    
    
    
    for indicator in typescript_indicators:
        if (project_path_obj / indicator).exists():
            # logger.info(f"Detected TypeScript/JavaScript project (found {indicator})")
            return 'typescript'
    
    for indicator in python_indicators:
        if (project_path_obj / indicator).exists():
            # logger.info(f"Detected Python project (found {indicator})")
            return 'python'

    # Check for .ts or .js files
    if list(project_path_obj.rglob("*.ts")) or list(project_path_obj.rglob("*.js")):
        # logger.info("Detected TypeScript/JavaScript project (found .ts/.js files)")
        return 'typescript'
    
    # Check for .py files
    if list(project_path_obj.rglob("*.py")):
        # logger.info("Detected Python project (found .py files)")
        return 'python'
    

    
    
    logger.warning("Could not determine project type")
    return 'unknown'


def build_python_database(project_path: str, database_path: str = '', 
                         codeql_path: str = "codeql", language: str = "python", overwrite: bool = False) -> bool:
    """
    Build a CodeQL database for a Python project.
    
    Args:
        project_path: Path to the Python project
        database_path: Path where the database should be created
        codeql_path: Path to the CodeQL CLI executable
        language: CodeQL language identifier (default: "python")
        
    Returns:
        bool: True if successful, False otherwise
    """
    if database_path == '':
        project_path = os.path.abspath(project_path)
        project_name = os.path.basename(project_path)
        database_path = os.path.join(project_path, project_name + '_codeql')

    try:
        logger.info(f"Building Python CodeQL database for {project_path}")
        
        # Create database directory if it doesn't exist
        if not os.path.exists(database_path):
            os.makedirs(database_path)
        elif overwrite:
            shutil.rmtree(database_path)
            os.makedirs(database_path)
        else:
            logger.warning(f"Database directory {database_path} already exists. Use --overwrite to overwrite it.")
            return True
        
        # Initialize the database
        init_cmd = [
            codeql_path, "database", "create",
            "--language=" + language,
            "--source-root=" + project_path,
            database_path
        ]

        logger.info(f"Running: {' '.join(init_cmd)}")
        env = os.environ.copy()
        env["CODEQL_EXTRACTOR_PYTHON_DISABLE_AUTOMATIC_VENV_EXCLUDE"] = '1'
        result = subprocess.run(init_cmd, capture_output=True, text=True, check=True, env=env)
        logger.info("Database created successfully")

        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Error building Python database: {e}")
        # logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error building Python database: {e}")
        return False


def build_typescript_database(project_path: str, database_path: str = '',
                            codeql_path: str = "codeql", language: str = "javascript-typescript", overwrite: bool = False) -> bool:
    """
    Build a CodeQL database for a TypeScript/JavaScript project.
    
    Args:
        project_path: Path to the TypeScript/JavaScript project
        database_path: Path where the database should be created
        codeql_path: Path to the CodeQL CLI executable
        language: CodeQL language identifier (default: "javascript")
        
    Returns:
        bool: True if successful, False otherwise
    """
    if database_path == '':
        project_path = os.path.abspath(project_path)
        project_name = os.path.basename(project_path)
        database_path = os.path.join(project_path, project_name + '_codeql')

    try:
        logger.info(f"Building TypeScript/JavaScript CodeQL database for {project_path}")
        
        # Create database directory if it doesn't exist
        if not os.path.exists(database_path):
            os.makedirs(database_path)
        elif overwrite:
            shutil.rmtree(database_path)
            os.makedirs(database_path)
        else:
            logger.warning(f"Database directory {database_path} already exists. Use --overwrite to overwrite it.")
            return False
        
        # Initialize the database
        init_cmd = [
            codeql_path, "database", "create",
            "--language=" + language,
            "--source-root=" + project_path,
            database_path
        ]
        
        logger.info(f"Running: {' '.join(init_cmd)}")
        result = subprocess.run(init_cmd, capture_output=True, text=True, check=True)
        logger.info("Database initialized successfully")
        
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"Error building TypeScript database: {e}")
        # logger.error(f"stdout: {e.stdout}")
        logger.error(f"stderr: {e.stderr}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error building TypeScript database: {e}")
        return False


def build_database(project_path: str, project_type: Optional[str] = None, database_path: str = '',codeql_path: str = "", force_rebuild: bool = False) -> bool:
    """
    Build a CodeQL database for the specified project.
    
    Args:
        project_path: Path to the project root
        database_path: Path where the database should be created (optional)
        project_type: Type of project ('python' or 'typescript', optional)
        codeql_path: Path to the CodeQL CLI executable
        
    Returns:
        bool: True if successful, False otherwise
    """
    if codeql_path == '':
        codeql_path = os.getenv('CODEQL_PATH', '')  # Provide empty string as default
    if not codeql_path:  # Check for empty string
        logger.error("CODEQL_PATH environment variable is not set")
        return False

    # Check if CodeQL is available
    if not check_codeql_installation(codeql_path):
        logger.error("CodeQL CLI not found or not working")
        return False
    
    # Validate project path
    if not os.path.exists(project_path):
        logger.error(f"Project path does not exist: {project_path}")
        return False    
    
    # Determine project type if not provided
    if project_type is None:
        project_type = detect_project_type(project_path)
        if project_type is None:
            logger.error("Could not determine project type")
            return False    

    
    # Build database based on project type
    if project_type == 'python':
        return build_python_database(project_path, database_path=database_path, codeql_path=codeql_path, overwrite=force_rebuild)
    elif project_type == 'typescript':
        return build_typescript_database(project_path, database_path=database_path, codeql_path=codeql_path, overwrite=force_rebuild)
    else:
        logger.error(f"Unsupported project type: {project_type}")
        return False

def run_codeql_query(database_path: str, query_path: str, codeql_path: str, output_path: str) -> Dict:
    """
    Execute a CodeQL query on the specified database.

    Args:
        database_path: Path to the CodeQL database
        query_path: Path to the CodeQL query file
        codeql_path: Path to the CodeQL CLI executable

    """    
    bqrs_path = os.path.join(output_path, 'results.bqrs')
    try:
        command = [
            codeql_path, 'query', 'run',
            '--database', database_path,
            '--output', bqrs_path,
            query_path
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        
        # Parse results from BQRS format
        bqrs_result = subprocess.run([
            codeql_path, 'bqrs', 'decode',
            '--format=json',
            bqrs_path  
        ], capture_output=True, text=True, check=True)
        
        results = json.loads(bqrs_result.stdout)
        logger.error(f"Command: {' '.join(command)}")
        
        return results
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Command: {' '.join(command)}")
        logger.error(f"Error running query: {e.stderr}")
        return {}


def run_call_graph_analysis(database_path: str, query_path: str, codeql_path: str, output_path: str, project_type: str) -> str:
    """
    Execute a CodeQL query on the specified database.

    Args:
        database_path: Path to the CodeQL database
        query_path: Path to the CodeQL query file
        codeql_path: Path to the CodeQL CLI executable
        
    """    

    logger.info(f"Running call graph analysis for {database_path}")
    try:
        #Todo: remove existing query cache

        command = [
            codeql_path, 'database', 'analyze', 
            '--format', 'dot', '-o', output_path,
            '--dot-location-url-format', "{path}:{start:line}:{start:column}:{end:line}:{end:column}",
            database_path, query_path
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        # codeql_logger.info(f"Result: {result.stdout}")
        if "No need to rerun" in result.stderr:
            logger.warning(f"call graph analysis use cached result")
        if project_type == 'python':
            tmp_dir = "python_queries"
        elif project_type == 'typescript':
            tmp_dir = "typescript_queries"
        else:
            logger.error(f"Unsupported project type: {project_type}")
            return ""
        query_name = os.path.basename(query_path)
        dot_path = os.path.join(output_path, tmp_dir, query_name + '.dot')
        if not os.path.exists(dot_path):
            logger.error(f"Dot file generated failed: {dot_path}")
            return ""

        # graphs = pydot.graph_from_dot_file(dot_path)
        return dot_path
            
    except subprocess.CalledProcessError as e:
        logger.error(f"Command: {' '.join(command)}")
        logger.error(f"Error running CodeQL query: {e.stderr}")
        return ""


def identify_entry_points(project_path: str, project_type: str|None, codeql_path: str = "", result_path: str = "") -> Dict:
    """
    Identify entry points for the project.

    Args:
        database_path: Path to the CodeQL database
        project_type: Type of project ('python' or 'typescript')
        codeql_path: Path to the CodeQL CLI executable
    """
    logger.info(f"Identifying entry points for {project_path}")
    if project_type == 'typescript':
        query_path = os.path.join(os.path.dirname(__file__), 'codeql_queries', 'typescript_queries', 'entry_identification_ts.ql')
    elif project_type == 'python':
        query_path = os.path.join(os.path.dirname(__file__), 'codeql_queries', 'python_queries', 'entry_identification_py.ql')
    else:
        logger.error(f"Unsupported project type: {project_type}")  
        return {}
    project_dir = os.path.basename(os.path.abspath(project_path))
    database_path = os.path.join(project_path, project_dir + '_codeql')
    results = run_codeql_query(database_path, query_path, codeql_path, result_path)
    if results == {}:
        logger.error("No entry points found")
        return {}
    result_file_path = os.path.join(result_path, 'entry_points_raw.json')
    with open(result_file_path, 'w') as f:
        json.dump(results, f)
    # Parse the results
    entry_points = {}
    
    # Extract tuples from the results
    if 'tuples' in results['#select']:
        for tuple_data in results['#select']['tuples']:
            if len(tuple_data) >= 4:
                tool_name = tuple_data[0]           # Tool name
                file_path = tuple_data[1]['label']  # File path
                line_start = tuple_data[2]          # Start line
                line_end = tuple_data[3]            # End line  
                
                # Create entry point structure
                entry_point = {
                    "file" : file_path,
                    "line_start": int(line_start),
                    "line_end": int(line_end),
                    "tool_name": tool_name
                }
                
                # Use tool name as key, handle duplicates by appending number
                entry_points[tool_name] = entry_point
    # Save to JSON file
    entry_points_path = os.path.join(result_path, 'entry_points.json')
    with open(entry_points_path, 'w') as f:
        json.dump(entry_points, f, indent=2)
    
    logger.info(f"Found {len(entry_points)} entry points")
    return entry_points


    
def build_call_graph(project_path: str, project_type: str, result_path: str = "", codeql_path: str = "") -> Dict:
    """
    Build the call graph for the specified entry points.
    """
    logger.info(f"Building call graph for {project_path}")
    if project_type == 'python':
        query_path = os.path.join(os.path.dirname(__file__), 'codeql_queries', 'python_queries', 'call_graph_py_g.ql')
    elif project_type == 'typescript':
        query_path = os.path.join(os.path.dirname(__file__), 'codeql_queries', 'typescript_queries', 'call_graph_ts_g.ql')
    else:
        logger.error(f"Unsupported project type for call graph analysis: {project_type}")
        return {}
    project_dir = os.path.basename(os.path.abspath(project_path))
    database_path = os.path.join(project_path, project_dir + '_codeql')

    if codeql_path == '':
        codeql_path = os.getenv('CODEQL_PATH', '') 
    if codeql_path == '':
        logger.error("CODEQL_PATH environment variable is not set")
        return {}
    dot_dir = os.path.join(result_path, 'codeql_call_graph.dot')
    dot_file_path = run_call_graph_analysis(database_path, query_path, codeql_path, dot_dir, project_type)

    if dot_file_path == "":
        logger.error("No call graph dot file generated")
        return {}   
    
    graph_json = parse_dot_graph_to_json(dot_file_path)

    # Load source code for each node and add it as an attribute
    for node_id, node_data in graph_json.items():
        file_path = node_data.get("path", "")
        try:
            # The file_path in each node is in the format {path}:{start:line}:{start:column}:{end:line}:{end:column}
            actual_path = file_path.split(':', 1)[0]
            if actual_path.startswith("/"):
                actual_path = actual_path[1:]
            abs_file_path = os.path.join(project_path, actual_path)
            with open(abs_file_path, 'r', encoding='utf-8') as src_file:
                # Load only the relevant lines and columns for concise code
                # file_path format: {path}:{start_line}:{start_col}:{end_line}:{end_col}
                    _, start_line, start_col, end_line, end_col = file_path.rsplit(':', 4)
                    start_line = int(start_line)
                    start_col = int(start_col)
                    end_line = int(end_line)
                    end_col = int(end_col)
                    src_lines = src_file.readlines()
                    if start_line == end_line:
                        # Single line
                        code = src_lines[start_line - 1][start_col - 1:end_col]
                    else:
                        code_lines = []
                        code_lines.append(src_lines[start_line - 1][start_col - 1:])
                        if end_line - start_line > 1:
                            code_lines.extend(src_lines[start_line:end_line - 1])
                        code_lines.append(src_lines[end_line - 1][:end_col])
                        code = ''.join(code_lines)
                    node_data["source_code"] = code
        except Exception as e:
            logger.error(f"Error loading source code for {abs_file_path} : {start_line} {start_col} {end_line} {end_col}")
            node_data["source_code"] = f"Could not load source code: {e}"
    with open(os.path.join(result_path, 'call_graph.json'), 'w') as f:
        json.dump(graph_json, f, indent=2)
    logger.info(f"Call graph built successfully")
    return graph_json


def parse_dot_graph_to_json(dot_file_path: str) -> Dict:
    """
    Parse a dot file and convert it to JSON format.
    
    Args:
        dot_file_path: Path to the dot file
        
    Returns:
        Dictionary containing nodes and edges
    """
    import re
    nodes = {}
    try:
        with open(dot_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        # Pattern: node_id[label="node_description"; href="path"; ];
        # The label may contain escaped double quotes (\") which can interfere with the regex.
        # Use a non-greedy match for the label and href, and allow for escaped quotes inside.
        node_pattern = r'(\d+)\[label="((?:[^"\\]|\\.)*?)";\s*href="((?:[^"\\]|\\.)*?)";\s*\];'
        node_matches = re.findall(node_pattern, content)
        path_set = {}
        node_index = {}
        index_cnt = 0
        for node_id, label, href in node_matches:
            clean_label = label.replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\')
            if href in path_set:
                node_index[int(node_id)] = path_set[href]
                node_id = path_set[href]
            else:
                path_set[href] = index_cnt
                node_index[int(node_id)] = index_cnt
                node_id = index_cnt
                index_cnt += 1
            nodes[node_id] = {
                "des": clean_label,
                "path": href,
                "node_id": node_id,
                "successors": []
            }
        
        # Parse edges
        # Pattern: source -> target[label="edge_label"; ];
        edge_pattern = r'(\d+)\s*->\s*(\d+)\[label="([^"]+)";\s*\];'
        edge_matches = re.findall(edge_pattern, content)
        for source, target, label in edge_matches:
            source = node_index[int(source)]
            target = node_index[int(target)]
            nodes[source]['successors'].append(target)
        if len(nodes) == 0:
            logger.error(f"No nodes found in dot file: {dot_file_path}")
            return {}
        return nodes
    except FileNotFoundError:
        logger.error(f"Dot file not found: {dot_file_path}")
        return {}
    except Exception as e:
        logger.error(f"Error parsing dot file: {e}")
        return {}

def main():
    """Example usage of the CodeQL database functions."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Build CodeQL databases for Python and TypeScript projects")
    parser.add_argument("project_path", help="Path to the project root")
    parser.add_argument("--database-path", help="Path where the database should be created")
    parser.add_argument("--project-type", choices=['python', 'typescript'], 
                       help="Type of project (auto-detected if not specified)")
    parser.add_argument("--codeql-path", default="codeql", 
                       help="Path to CodeQL CLI executable")
    
    args = parser.parse_args()
    
    success = build_database(
        project_path=args.project_path,
        project_type=args.project_type,
        database_path=args.database_path,
        codeql_path=args.codeql_path
    )
    
    if success:
        print("✅ CodeQL database built successfully!")
        sys.exit(0)
    else:
        print("❌ Failed to build CodeQL database")
        sys.exit(1)


if __name__ == "__main__":
    main()

