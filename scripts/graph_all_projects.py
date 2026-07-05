import json
import os
import subprocess
import random
import numpy as np
from typing import List, Dict, Any
import argparse

def weighted_random_sample(servers: List[Dict[str, Any]], sample_size: int = 100) -> List[Dict[str, Any]]:
    """
    Uses a normal distribution approach where the weight is based on log(stars + 1).
    """
    if len(servers) <= sample_size:
        return servers
    
    # Calculate weights based on stars (using log to reduce extreme differences)
    weights = []
    for server in servers:
        stars = server.get('stars', 0)
        # Use log(stars + 1) to create a more balanced distribution
        # Add 1 to avoid log(0) and give some weight to projects with 0 stars
        weight = np.log(stars + 1) + 1  # +1 ensures minimum weight
        weights.append(weight)
    
    # Normalize weights to sum to 1
    total_weight = sum(weights)
    normalized_weights = [w / total_weight for w in weights]
    
    # Perform weighted random sampling
    selected_indices = np.random.choice(
        len(servers), 
        size=sample_size, 
        replace=False,  # No replacement to avoid duplicates
        p=normalized_weights
    )
    
    selected_servers = [servers[i] for i in selected_indices]
    
    # Sort by stars for better visualization
    selected_servers.sort(key=lambda x: x.get('stars', 0), reverse=True)
    
    return selected_servers

def analyze_sample_distribution(original_servers: List[Dict[str, Any]], sampled_servers: List[Dict[str, Any]]):
    """
    Analyze the distribution of the sampled servers compared to the original.
    """
    print(f"Original dataset: {len(original_servers)} projects")
    print(f"Sampled dataset: {len(sampled_servers)} projects")
    
    # Calculate star statistics
    original_stars = [s.get('stars', 0) for s in original_servers]
    sampled_stars = [s.get('stars', 0) for s in sampled_servers]
    
    print(f"\nOriginal dataset star statistics:")
    print(f"  Mean: {np.mean(original_stars):.2f}")
    print(f"  Median: {np.median(original_stars):.2f}")
    print(f"  Max: {max(original_stars)}")
    print(f"  Min: {min(original_stars)}")
    
    print(f"\nSampled dataset star statistics:")
    print(f"  Mean: {np.mean(sampled_stars):.2f}")
    print(f"  Median: {np.median(sampled_stars):.2f}")
    print(f"  Max: {max(sampled_stars)}")
    print(f"  Min: {min(sampled_stars)}")
    
    # Show top 10 sampled projects
    print(f"\nTop 10 sampled projects by stars:")
    for i, server in enumerate(sampled_servers[:10]):
        print(f"  {i+1}. {server['name']}: {server.get('stars', 0)} stars")

def analyze_project(server: Dict[str, Any], server_name: str):
    try:
        results = subprocess.run(["python3", "call_graph_analyze.py", "--url", server["repo_url"], "--force_rebuild", "--project_name", server_name])
        if results.returncode != 0:
            raise subprocess.CalledProcessError(results.returncode, results.args)
        server['analysis_result'] = 'success'
        # Clear retry count.
        if 'retry_count' in server:
            del server['retry_count']
        # analysis_results[server_name] = 'success'
    except subprocess.CalledProcessError as e:
        print(f"Error analyzing {server_name}: {e}")
        if hasattr(e, 'stderr') and e.stderr:
            print(e.stderr)
        if e.returncode == 1:
            server['analysis_result'] = "git clone error"
        elif e.returncode == 2:
            server['analysis_result'] = "project type error"
        elif e.returncode == 3:
            server['analysis_result'] = "entry points not found"
        elif e.returncode == 4:
            server['analysis_result'] = "call graph build error"
        elif e.returncode == 5:
            server['analysis_result'] = "invoked functions analysis error"
        elif e.returncode == 6:
            server['analysis_result'] = "build codeql database error"
        else:
            server['analysis_result'] = "unknown error"
        # Increase retry count.
        if 'retry_count' not in server:
            server['retry_count'] = 0
        server['retry_count'] += 1
    return server

def should_retry_error(error_type: str, retryable_errors: List[str]) -> bool:
    """Determine whether an error type should be retried."""
    # Permanent errors should not be retried.
    permanent_errors = [
        'project type error',
        'entry points not found',
        'unknown error'
    ]
    
    # Return False directly for permanent errors.
    if error_type in permanent_errors:
        return False
    
    # If retryable error types are specified, retry only those errors.
    if retryable_errors:
        return error_type in retryable_errors
    
    # If not specified, retry all non-permanent errors.
    return True


if __name__ == "__main__":
    # Set random seed for reproducibility
    parser = argparse.ArgumentParser()
    parser.add_argument('--clean', help="clean all failed git repos", action='store_true')
    parser.add_argument('--sample', help="sample part of MCP servers for analyze, default is all servers", type=int, default=10000000)
    parser.add_argument('--result_file', help="result file", type=str, default="results/0-results/analyzed_projects.json")
    parser.add_argument('--retry', help="retry failed projects, default is no retry", action='store_true')
    parser.add_argument('--retry_count', help="maximum retry count for failed projects, default is 3", type=int, default=3)
    parser.add_argument('--retry_errors', help="comma-separated list of error types to retry (e.g., 'git clone error,build codeql database error'). If not specified, retry all errors", type=str, default="")
    parser.add_argument('--auto_retry', help="automatically retry failed projects during main loop, default is False", action='store_true')
    parser.add_argument('--mcp_servers', '-m', help="json file for MCP server information", type=str, default="tool_analyzer/mcp_servers_analysis.json")
    # parser.add_argument('--seed', help="random seed", type=int, default=42)
    args = parser.parse_args()
    random.seed(42)
    np.random.seed(42)
    # sampled_server_file = f"Servers/sampled_projects_{args.sample}.json"
    # sample_size = 100
    if args.clean:
        with open(args.result_file, "r") as f:
            analysis_results = json.load(f)
        all_projects = os.listdir("Servers")
        for project in all_projects:
            if project == '0examples' or os.path.isfile(os.path.join("Servers", project)):
                continue
            if project in analysis_results and analysis_results[project]['analysis_result'] == 'success':
                continue
            else:
                subprocess.run(["rm", "-rf", os.path.join("Servers", project)])
        all_projects = os.listdir("results")
        for project in all_projects:
            if project.startswith("0examples") or project == "0-results":
                continue
            if os.path.isfile(os.path.join("results", project)):
                continue
            if project in analysis_results and analysis_results[project]['analysis_result'] == 'success':
                continue
            subprocess.run(["rm", "-rf", os.path.join("results", project)])
        exit(0)

    
    # Load the servers data
    with open(args.mcp_servers, "r") as f:
        servers = json.load(f)
    # Filter out projects with no stars data
    servers = [s for s in servers if 'stars' in s]
    success_number = 0
    analysis_results = {}
    if os.path.exists(args.result_file):
        with open(args.result_file, "r") as f:
            analysis_results = json.load(f)
        for project in analysis_results:
            if analysis_results[project]['analysis_result'] == 'success':
                success_number += 1
    if success_number > args.sample:
        print(f"Success number {success_number} > sample size {args.sample}, no need to sample")
        exit(0)
    else:
        print(f"Success number {success_number} < sample size {args.sample}, sampling")
    # Parse retryable error types.
    retryable_errors = []
    if args.retry_errors:
        retryable_errors = [e.strip() for e in args.retry_errors.split(',')]
    
    # If --retry is used, retry only failed projects.
    if args.retry:
        print(f"Starting retry for failed projects, maximum retry count: {args.retry_count}")
        if retryable_errors:
            print(f"Retrying only the following error types: {', '.join(retryable_errors)}")
        else:
            print("Retrying all error types")
        
        failed_projects = []
        for project in analysis_results:
            if analysis_results[project]['analysis_result'] != 'success':
                error_type = analysis_results[project]['analysis_result']
                retry_count = analysis_results[project].get('retry_count', 0)
                if should_retry_error(error_type, retryable_errors) and retry_count < args.retry_count:
                    failed_projects.append(project)
        
        print(f"Found {len(failed_projects)} projects that need retry")
        for i, project in enumerate(failed_projects, 1):
            print(f"[{i}/{len(failed_projects)}] Retrying project: {project}")
            server = analysis_results[project]
            server = analyze_project(server, project)
            analysis_results[project] = server
            if server['analysis_result'] == 'success':
                success_number += 1
                print(f"✓ Project {project} retry succeeded")
            else:
                retry_count = server.get('retry_count', 0)
                print(f"✗ Project {project} retry failed (retried {retry_count}/{args.retry_count} times)")
            # Ensure result directory exists.
            result_dir = os.path.dirname(args.result_file)
            if result_dir and not os.path.exists(result_dir):
                os.makedirs(result_dir, exist_ok=True)
            with open(args.result_file, "w", encoding="utf-8") as f:
                json.dump(analysis_results, f, indent=2, ensure_ascii=False)
        print("Retry completed")
        exit(0)
    
    sample = True
    if args.sample >= len(servers):
        args.sample = len(servers)
        print(f"Sample size {args.sample} is greater than the number of projects {len(servers)}, set sample size to {len(servers)}")
        sample = False
    index = 0

    # Queue of failed projects for --auto_retry.
    failed_projects_queue = []
    
    # When using sequential processing (sample=False), process all servers regardless of success_number
    # When using random sampling (sample=True), respect the success_number limit
    while (index < len(servers)) and (sample == False or (sample == True and success_number <= args.sample)) or (args.auto_retry and len(failed_projects_queue) > 0):
        # If automatic retry is enabled and failed projects exist, retry them first.
        if args.auto_retry and len(failed_projects_queue) > 0:
            project_name = failed_projects_queue.pop(0)
            server = analysis_results[project_name]
            error_type = server['analysis_result']
            retry_count = server.get('retry_count', 0)
            
            if should_retry_error(error_type, retryable_errors) and retry_count < args.retry_count:
                print(f"[auto retry {retry_count + 1}/{args.retry_count}] Retrying project: {project_name} (error type: {error_type})")
                server = analyze_project(server, project_name)
                analysis_results[project_name] = server
                if server['analysis_result'] == 'success':
                    success_number += 1
                    print(f"✓ Project {project_name} automatic retry succeeded")
                else:
                    new_retry_count = server.get('retry_count', 0)
                    if new_retry_count < args.retry_count:
                        # Requeue if retries remain.
                        failed_projects_queue.append(project_name)
                    print(f"✗ Project {project_name} automatic retry failed (retried {new_retry_count}/{args.retry_count} times)")
            # Ensure result directory exists.
            result_dir = os.path.dirname(args.result_file)
            if result_dir and not os.path.exists(result_dir):
                os.makedirs(result_dir, exist_ok=True)
            with open(args.result_file, "w", encoding="utf-8") as f:
                json.dump(analysis_results, f, indent=2, ensure_ascii=False)
            continue
        
        # Perform weighted random sampling
        if sample:
            server = weighted_random_sample(servers, sample_size=1)[0]
        else:
            server = servers[index]
            index += 1
        server_name = '_'.join(server["name"].split('/')[-2:])
        # server_name = '_'.join(server["name"].split('/')[3:5])
        if server_name in analysis_results:
            continue

        server = analyze_project(server, server_name)
        analysis_results[server_name] = server
        if server['analysis_result'] == 'success':
            success_number += 1
        elif args.auto_retry:
            # If automatic retry is enabled, add failed projects to the retry queue.
            error_type = server['analysis_result']
            retry_count = server.get('retry_count', 0)
            if should_retry_error(error_type, retryable_errors) and retry_count < args.retry_count:
                failed_projects_queue.append(server_name)
        # Ensure result directory exists
        result_dir = os.path.dirname(args.result_file)
        if result_dir and not os.path.exists(result_dir):
            os.makedirs(result_dir, exist_ok=True)
        with open(args.result_file, "w", encoding="utf-8") as f:
            json.dump(analysis_results, f, indent=2, ensure_ascii=False)
        
