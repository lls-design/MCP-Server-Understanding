#!/usr/bin/env python3
"""
Quickly cancel a batch job.
Usage: python cancel_batch.py <batch_id>
"""
import sys
import logging
from utils.batch_call import get_openai_client, cancel_batch_job, query_batch_status

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("cancel_batch")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python cancel_batch.py <batch_id>")
        print("Example: python cancel_batch.py batch_3fd3755c-1b26-403d-9e33-c34054f684fa")
        print("\nOr use interactive mode:")
        print("  python cancel_batch.py")
        sys.exit(1)
    
    batch_id = sys.argv[1]
    
    try:
        client = get_openai_client()
        
        # Query the current status first.
        print(f"\nQuerying job status...")
        status_info = query_batch_status(batch_id, client)
        print(f"Current status: {status_info.get('status')}")
        if 'request_counts' in status_info and status_info['request_counts']:
            print(f"Request counts: {status_info['request_counts']}")
        
        # Confirm cancellation.
        print(f"\nPreparing to cancel job: {batch_id}")
        confirm = input("Confirm cancellation? (yes/no): ").strip().lower()
        if confirm != 'yes':
            print("Operation cancelled")
            sys.exit(0)
        
        # Perform cancellation.
        result = cancel_batch_job(batch_id, client)
        print(f"\n✓ Job cancelled successfully!")
        print(f"Job ID: {result['id']}")
        print(f"Job status: {result['status']}")
        if result.get('cancelled_at'):
            print(f"Cancelled at: {result['cancelled_at']}")
            
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Cancellation failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        sys.exit(1)
