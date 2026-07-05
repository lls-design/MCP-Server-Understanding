#!/usr/bin/env python3
"""
Query batch job lists.
Usage:
  python list_batches.py                    # List all jobs
  python list_batches.py --status completed # List only completed jobs
  python list_batches.py --limit 10          # Show only 10 jobs
"""
import sys
import argparse
import logging
from datetime import datetime
from utils.batch_call import get_openai_client, list_batch_jobs

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("list_batches")


def format_timestamp(timestamp):
    """Format a timestamp."""
    if timestamp is None:
        return "N/A"
    try:
        if isinstance(timestamp, (int, float)):
            dt = datetime.fromtimestamp(timestamp)
        else:
            dt = datetime.fromisoformat(str(timestamp).replace('Z', '+00:00'))
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except:
        return str(timestamp)


def print_batch_list(batches):
    """Print the job list."""
    if not batches:
        print("\nNo batch jobs found")
        return
    
    print(f"\nFound {len(batches)} batch jobs:\n")
    print("=" * 120)
    
    for idx, batch in enumerate(batches, 1):
        print(f"\n[{idx}] Job ID: {batch['id']}")
        print(f"    Status: {batch['status']}")
        print(f"    Created at: {format_timestamp(batch.get('created_at'))}")
        print(f"    Ended at: {format_timestamp(batch.get('ended_at'))}")
        
        if 'request_counts' in batch and batch['request_counts']:
            counts = batch['request_counts']
            total = counts.get('total', 0)
            completed = counts.get('completed', 0)
            failed = counts.get('failed', 0)
            print(f"    Request counts: total={total}, completed={completed}, failed={failed}")
            if total > 0:
                progress = (completed / total) * 100
                print(f"    Progress: {progress:.1f}%")
        
        if batch.get('input_file_id'):
            print(f"    Input file ID: {batch['input_file_id']}")
        if batch.get('output_file_id'):
            print(f"    Output file ID: {batch['output_file_id']}")
        if batch.get('error_file_id'):
            print(f"    Error file ID: {batch['error_file_id']}")
        
        print("-" * 120)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query batch job list")
    parser.add_argument("--after", type=str, help="Last batch job ID from the previous page, used for pagination")
    parser.add_argument("--limit", type=int, help="Maximum number of jobs to return")
    parser.add_argument("--status", type=str, help="Filter by job status, comma-separated, e.g. completed,expired")
    parser.add_argument("--input_file_ids", type=str, help="Filter by input file IDs, comma-separated")
    parser.add_argument("--ds_name", type=str, help="Filter by job name")
    parser.add_argument("--create_after", type=str, help="Creation time filter start, format: YYYYMMDDHHmmss")
    parser.add_argument("--create_before", type=str, help="Creation time filter end, format: YYYYMMDDHHmmss")
    parser.add_argument("--all", action="store_true", help="Fetch all jobs with automatic pagination")
    
    args = parser.parse_args()
    
    try:
        client = get_openai_client()
        
        if args.all:
            # Fetch all jobs with automatic pagination.
            print("Fetching all batch jobs with automatic pagination...")
            all_batches = []
            after = None
            
            while True:
                batches = list_batch_jobs(
                    client=client,
                    after=after,
                    limit=100,  # Fetch 100 jobs per request.
                    status=args.status,
                    input_file_ids=args.input_file_ids,
                    ds_name=args.ds_name,
                    create_after=args.create_after,
                    create_before=args.create_before
                )
                
                if not batches:
                    break
                
                all_batches.extend(batches)
                print(f"Fetched {len(all_batches)} jobs...", end='\r')
                
                # Check whether more pages remain.
                if len(batches) < 100:
                    break
                
                # Set the after parameter for the next page.
                after = batches[-1]['id']
            
            print(f"\nFetched {len(all_batches)} jobs in total")
            print_batch_list(all_batches)
        else:
            # Single query.
            batches = list_batch_jobs(
                client=client,
                after=args.after,
                limit=args.limit,
                status=args.status,
                input_file_ids=args.input_file_ids,
                ds_name=args.ds_name,
                create_after=args.create_after,
                create_before=args.create_before
            )
            print_batch_list(batches)
            
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Query failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
