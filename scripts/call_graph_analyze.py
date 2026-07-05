from ast import Tuple
import os
import json
import subprocess
from typing import List, Dict, Set, Tuple
import sys
from dotenv import load_dotenv
from codeql_analyzer.codeql_executor import build_database, detect_project_type, identify_entry_points, build_call_graph
from tool_analyzer.api_collection import collect_invoked_functions
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("call_graph_analyze")

def clone_repo(url, repo_path):
    move = False
    # Remove URL anchor (e.g., #readme)
    if '#' in url:
        url = url[:url.index('#')]
    
    # Remove trailing slash
    if url.endswith('/'):
        url = url[:-1]
    
    # Handle file URLs - remove the file part, keep only the directory
    if ".ts" in url or ".py" in url or ".md" in url or ".js" in url:
        if url.endswith(('.ts', '.py', '.md', '.js')):
            url = url[:url.rfind('/')]
    
    # Handle tree/master, tree/main, blob/master, blob/main
    if 'tree/main' in url:
        git_url = url[:url.index('tree/main')]
        source_path = url[url.index('tree/main')+len('tree/main'):]
        move = True
    elif 'tree/master' in url:
        git_url = url[:url.index('tree/master')]
        source_path = url[url.index('tree/master')+len('tree/master'):]
        move = True
    elif "blob/main" in url:
        git_url = url[:url.index('blob/main')]
        source_path = url[url.index('blob/main')+len('blob/main'):]
        move = True
    elif "blob/master" in url:
        git_url = url[:url.index('blob/master')]
        source_path = url[url.index('blob/master')+len('blob/master'):]
        move = True
    else:
        git_url = url
        source_path = ''
    
    # Clean up git_url - remove trailing slash if present
    if git_url.endswith('/'):
        git_url = git_url[:-1]
    
    # Ensure git_url ends with .git for GitHub URLs (optional, but cleaner)
    if 'github.com' in git_url and not git_url.endswith('.git'):
        # Don't add .git if it's already there or if it's a subdirectory path
        pass  # git clone works with or without .git
    
    try:
        subprocess.run(['git', 'clone', git_url, repo_path], check=True)
        # subprocess.run(['git', 'checkout', source_path], check=True, cwd=repo_path)
    except subprocess.CalledProcessError as e:
        
        if os.path.exists(repo_path):
            subprocess.run(['rm', '-rf', repo_path], check=True)
        logger.error(f'Failed to clone repository: {e}')
        exit(1)
    
    if move:
        if source_path.startswith('/'):
            source_path = source_path[1:]
        try:
            tmp_path = repo_path
            if tmp_path.endswith('/'):
                tmp_path = tmp_path[:-1]
            tmp_path = tmp_path + "_tmp"
            subprocess.run(['mv', os.path.join(repo_path, source_path), tmp_path], check=True)
            subprocess.run(['rm', '-rf', repo_path], check=True)
            subprocess.run(['mv', tmp_path, repo_path], check=True)
        except subprocess.CalledProcessError as e:
            if os.path.exists(repo_path):
                subprocess.run(['rm', '-rf', repo_path], check=True)
            if os.path.exists(tmp_path):
                subprocess.run(['rm', '-rf', tmp_path], check=True)
            logger.error(f'Failed to move repository: {e}')
            exit(1)
    

if __name__ == '__main__':
    load_dotenv('.env')  # Load environment variables from .env file
    import argparse
    parser = argparse.ArgumentParser(description='Analyze a git repo for MCP tool entry points')
    parser.add_argument('--url', "-u", help='Git URL to analyze', default='')
    parser.add_argument('--project_path', "-p", help='Project path', default='')
    parser.add_argument('--project_dir', "-w", help='Output file', default='./Servers')
    parser.add_argument('--result_dir', "-r", help='Output file', default='./results')
    parser.add_argument('--force_rebuild', "-f", help='Force rebuild the database', action='store_true')
    parser.add_argument('--project_name', "-n", help='Project name, if not specified, will be inferred from the git URL and project path', default='')

    parser.add_argument('--project_type', "-t", help='Project type', default='unknown')
    args = parser.parse_args()


    
    
    if not os.path.exists(args.project_dir):
        os.makedirs(args.project_dir)
    if args.url == '' and args.project_path == '':
        logger.error('Please specify either a git URL or a project path.')
        exit(1)
    if args.url != '' and args.project_path != '':
        logger.error('Please specify either a git URL or a project path, not both.')
        exit(1)
    if args.url != '':
        # if "tree/main" in args.url:
        if args.project_name != '':
            repo_name = args.project_name
        else:
            repo_name = args.url.split('/')[3:5]
            repo_name = '_'.join(repo_name)
        if repo_name.endswith('.git'):
            repo_name = repo_name[:-4]
        
        repo_path = os.path.join(args.project_dir, repo_name)
        if not os.path.exists(repo_path):
            clone_repo(args.url, repo_path)
           
    else:
        repo_path = args.project_path
        if repo_path.endswith('/'):
            repo_path = repo_path[:-1]
        if args.project_name != '':
            repo_name = args.project_name
        else:
            repo_name = os.path.basename(repo_path)

    # Build CodeQL database
    project_type = args.project_type
    if project_type == 'unknown':
        project_type = detect_project_type(repo_path)
        if project_type == 'unknown':
            logger.error('Unknown project type. Please specify the project type manually.')
            exit(2)
    logger.info(f'Project type: {project_type}')

    # Add CodeQL path to system PATH
    codeql_path = os.getenv('CODEQL_PATH', '')

    
    
    result_path = os.path.join(args.result_dir, repo_name)
    if not os.path.exists(result_path):
        os.makedirs(result_path)

    # console_handler = logging.StreamHandler()
    file_handler = logging.FileHandler(os.path.join(result_path, 'call_graph_analyze.log'))
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    logger.addHandler(file_handler)
    # logger.addHandler(console_handler)

    if codeql_path:
        os.environ['PATH'] = f"{codeql_path}:{os.environ['PATH']}"
    build_success = build_database(repo_path, database_path='', project_type=project_type, codeql_path=codeql_path, force_rebuild=args.force_rebuild)
    if not build_success:
        logger.error('Build database failed!!! Analysis failed.')
        exit(6)

    # Identify entry points
    entry_points = identify_entry_points(repo_path, project_type, codeql_path=codeql_path, result_path=result_path)
    if entry_points == {}:
        logger.error('No entry points found!!! Analysis failed.')
        exit(3)

    call_graphs_json = build_call_graph(project_path=repo_path, project_type=project_type, result_path=result_path, codeql_path=codeql_path)

    if call_graphs_json == {}:
        logger.error('No call graph found!!! Analysis failed.')
        exit(4)
    
    invoked_functions = collect_invoked_functions(call_graphs_json, entry_points)
    if invoked_functions == {}:
        logger.error('No invoked functions found!!! Analysis failed.')
        exit(5)
    
    with open(os.path.join(result_path, 'invoked_functions.json'), 'w') as f:
        json.dump(invoked_functions, f, indent=2)
    

