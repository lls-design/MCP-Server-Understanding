#!/usr/bin/env python3
"""
Classify APIs for all projects in batch using the batch interface.
"""
import os
import json
import argparse
import logging
import time
from pathlib import Path
from scripts.api_analyze import classify_api_of_a_project, safe_save_json, collect_apis_to_classify, apply_classification_results, prompt_api_classification
from utils.llm_call import get_openai_client, get_gemini_client
from utils.batch_call import batch_classify_apis

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("batch_classify")


def get_all_projects(results_dir="results", output_file="call_graph_labeled.json"):
    """Get all project directories."""
    results_path = Path(results_dir)
    if not results_path.exists():
        logger.error(f"Results directory does not exist: {results_dir}")
        return []
    
    projects = []
    for item in results_path.iterdir():
        if item.is_dir() and not item.name.startswith('.'):
            call_graph_path = item / output_file
            if call_graph_path.exists():
                projects.append(item.name)
            else:
                logger.warning(f"Project {item.name} is missing {output_file}, skipping")
    
    return sorted(projects)


def main():
    parser = argparse.ArgumentParser(description="Classify APIs for all projects in batch")
    parser.add_argument("--results_dir", "-r", type=str, default="results", 
                       help="Path to the results directory")
    parser.add_argument("--cache", type=str, default="tool_analyzer/api_cache.json",
                       help="API cache file path")
    parser.add_argument("--output_file", type=str, default="call_graph_labeled.json",
                       help="Output file name")
    parser.add_argument("--use_batch", action="store_true", default=True,
                       help="Use the batch interface (enabled by default)")
    parser.add_argument("--no_batch", dest="use_batch", action="store_false",
                       help="Disable the batch interface and call APIs one by one")
    parser.add_argument("--start_from", type=str, default=None,
                       help="Start processing from the specified project")
    parser.add_argument("--start_index", type=int, default=None,
                       help="Start from the specified 1-based index, e.g. 100 starts from project 100")
    parser.add_argument("--max_projects", type=int, default=None,
                       help="Maximum number of projects to process")
    parser.add_argument("--skip_classified", action="store_true", default=True,
                       help="Skip fully classified projects where all APIs have a category (enabled by default)")
    parser.add_argument("--no_skip_classified", dest="skip_classified", action="store_false",
                       help="Do not skip fully classified projects; process all projects")
    parser.add_argument("--prepare_only", action="store_true",
                       help="Only generate input JSONL without submitting a batch")
    parser.add_argument("--use_input", type=str, default=None,
                       help="Use an existing batch input JSONL file and skip generation")
    parser.add_argument("--save_input", type=str, default=None,
                       help="Save the generated batch input JSONL to the specified path")
    parser.add_argument("--shard", type=int, default=None, help="shard id (0-based)")
    parser.add_argument("--num-shards", type=int, default=None, help="total shards")
    
    args = parser.parse_args()
    
    # Initialize client.
    try:
        client = get_openai_client()
        logger.info("OpenAI/QWEN client initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize client: {e}")
        return
    
    # Get all projects.
    projects = get_all_projects(args.results_dir, args.output_file)
    
    if not projects:
        logger.error("No projects found")
        return
    
    logger.info(f"Found {len(projects)} projects")

    if args.shard is not None:
        if args.num_shards is None:
            logger.error("--shard requires --num-shards")
            return
        projects = [p for i, p in enumerate(projects) if i % args.num_shards == args.shard]
        logger.info(f"shard {args.shard}/{args.num_shards}: {len(projects)} projects")
    
    # Handle start project.
    if args.start_from:
        try:
            start_idx = projects.index(args.start_from)
            projects = projects[start_idx:]
            logger.info(f"Starting from project {args.start_from}")
        except ValueError:
            logger.warning(f"Project {args.start_from} not found; starting from the first project")
    
    # Handle start index.
    if args.start_index is not None:
        if args.start_index > 0:
            start_idx = args.start_index - 1  # Convert to 0-based index.
            if start_idx < len(projects):
                projects = projects[start_idx:]
                logger.info(f"Starting from project #{args.start_index} (project name: {projects[0] if projects else 'N/A'})")
            else:
                logger.warning(f"Start index {args.start_index} exceeds total projects {len(projects)}; no projects to process")
                projects = []
        else:
            logger.warning(f"Start index must be greater than 0, current value: {args.start_index}")
    
    # Limit project count.
    if args.max_projects:
        projects = projects[:args.max_projects]
        logger.info(f"Limiting project count to: {args.max_projects}")
    
    # If skipping classified projects is enabled, first check which projects need processing.
    if args.skip_classified:
        projects_to_process = []
        for project in projects:
            project_path = os.path.join(args.results_dir, project)
            call_graph_path = os.path.join(project_path, args.output_file)
            
            if not os.path.exists(call_graph_path):
                projects_to_process.append(project)
                continue
            
            try:
                with open(call_graph_path, 'r') as f:
                    call_graph = json.load(f)
                
                # Check whether there are unclassified APIs.
                has_unclassified = False
                for node_id in call_graph:
                    if not call_graph[node_id]['des'].startswith("CallNode"):
                        continue
                    if 'external_api' not in call_graph[node_id] or not call_graph[node_id]['external_api']:
                        continue
                    if 'category' not in call_graph[node_id]:
                        has_unclassified = True
                        break
                
                if has_unclassified:
                    projects_to_process.append(project)
                else:
                    logger.info(f"Project {project} is fully classified, skipping")
            except Exception as e:
                logger.warning(f"Failed to check project {project} status: {e}; processing this project")
                projects_to_process.append(project)
        
        projects = projects_to_process
        logger.info(f"Projects to process after filtering: {len(projects)}")
    
    if not projects:
        logger.info("No projects need processing")
        return
    
    logger.info(f"Starting batch classification, use batch interface: {args.use_batch}")
    logger.info(f"{'='*80}")
    
    # Statistics.
    success_count = 0
    fail_count = 0
    
    if args.use_batch:
        # New mode: collect APIs from all projects and call batch once.
        logger.info("Collecting APIs from all projects...")
        all_apis = []
        api_mapping = []  # Record project information for each API.
        
        for project in projects:
            apis = collect_apis_to_classify(project, args.cache, args.output_file)
            for api in apis:
                all_apis.append({
                    "api_name": api["api_name"],
                    "api_summary": api["api_summary"]
                })
                api_mapping.append({
                    "project": project,
                    "node_id": api["node_id"],
                    "api_name": api["api_name"]
                })
        
        if not all_apis:
            logger.info("No APIs need classification")
            return
        
        logger.info(f"Collected {len(all_apis)} APIs needing classification from {len(projects)} projects")

        # Determine input file path.
        input_file_path = args.use_input or args.save_input or f"batch_classify_input_{int(time.time())}.jsonl"

        # Generate the input file first if use_input is not specified.
        if not args.use_input:
            gen_info = batch_classify_apis(
                all_apis,
                prompt_api_classification,
                model="qwen-plus",
                input_file=input_file_path,
                generate_only=True,
                keep_files=True,
            )
            if isinstance(gen_info, dict):
                logger.info(f"Generated batch input file: {gen_info.get('input_file')}, {gen_info.get('count')} requests total")
            else:
                logger.info(f"Generated batch input file: {input_file_path}")
            if args.prepare_only:
                logger.info("Generate-only mode; exiting.")
                return
        else:
            logger.info(f"Using existing input file: {input_file_path}")

        logger.info("Starting batch call...")
        
        try:
            # Call all APIs in one batch.
            results = batch_classify_apis(
                all_apis,
                prompt_api_classification,
                model="qwen-plus",
                input_file=input_file_path,
                use_existing_input_file=True,
                keep_files=True
            )
            
            logger.info(f"Batch call completed, {len(results)} results total")
            logger.info("Assigning results to projects...")
            
            # Apply results grouped by project.
            for project in projects:
                try:
                    # Find results for this project.
                    project_indices = [i for i, m in enumerate(api_mapping) if m["project"] == project]
                    project_results = [results[i] for i in project_indices if i < len(results)]
                    project_mapping = [api_mapping[i] for i in project_indices]


                    if project_results:
                        apply_classification_results(
                            project,
                            project_results,
                            project_mapping,
                            args.cache,
                            args.output_file
                        )
                        success_count += 1
                        logger.info(f"✓ Project {project} classification completed")
                    else:
                        logger.warning(f"Project {project} has no corresponding results")
                        fail_count += 1
                        
                        
                except Exception as e:
                    fail_count += 1
                    logger.error(f"✗ Error processing project {project}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
            
            logger.info(f"\n{'='*80}")
            logger.info(f"Batch classification completed!")
            logger.info(f"Total: {len(projects)} projects")
            logger.info(f"Successful: {success_count}")
            logger.info(f"Failed: {fail_count}")
            logger.info(f"{'='*80}")
            
        except KeyboardInterrupt:
            logger.warning("\n\nInterrupted by user")
        except Exception as e:
            logger.error(f"Batch call failed: {e}")
            import traceback
            logger.error(traceback.format_exc())
    else:
        # Old mode: process projects one by one.
        try:
            for idx, project in enumerate(projects, 1):
                logger.info(f"\n{'='*80}")
                logger.info(f"Processing project [{idx}/{len(projects)}]: {project}")
                logger.info(f"{'='*80}")
                
                try:
                    call_graph = classify_api_of_a_project(
                        project,
                        client,
                        cache_path=args.cache,
                        output_file=args.output_file,
                    )
                    
                    if call_graph:
                        success_count += 1
                        logger.info(f"✓ Project {project} classification completed")
                    else:
                        fail_count += 1
                        logger.error(f"✗ Project {project} classification failed (empty result returned)")
                        
                except KeyboardInterrupt:
                    logger.warning("\nInterrupted by user")
                    raise
                except Exception as e:
                    fail_count += 1
                    logger.error(f"✗ Error processing project {project}: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    continue
        
        except KeyboardInterrupt:
            logger.warning("\n\nInterrupted by user")
        
        # Output statistics.
        logger.info(f"\n{'='*80}")
        logger.info(f"Batch classification completed!")
        logger.info(f"Total: {len(projects)} projects")
        logger.info(f"Successful: {success_count}")
        logger.info(f"Failed: {fail_count}")
        logger.info(f"{'='*80}")


if __name__ == "__main__":
    main()
