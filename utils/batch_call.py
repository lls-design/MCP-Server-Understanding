import json
import os
import time
from pathlib import Path
from typing import List, Dict, Optional
import logging
from openai import OpenAI
import dotenv
dotenv.load_dotenv(".env")

logger = logging.getLogger("batch_call")
logger.setLevel(logging.INFO)


def get_openai_client():
    """Get an OpenAI-compatible client for batch calls."""
    return OpenAI(
        api_key=os.getenv("QWEN_KEY"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def upload_file(client: OpenAI, file_path: str) -> str:
    """
    Upload a JSONL file containing request information.
    
    Args:
        client: OpenAI client instance.
        file_path: JSONL file path.
    
    Returns:
        File ID.
    """
    logger.info(f"Uploading JSONL request file: {file_path}")
    file_object = client.files.create(file=Path(file_path), purpose="batch")
    logger.info(f"File uploaded successfully, file ID: {file_object.id}")
    return file_object.id


def create_batch_job(client: OpenAI, input_file_id: str, endpoint: str = "/v1/chat/completions", completion_window: str = "24h") -> str:
    """
    Create a batch job.
    
    Args:
        client: OpenAI client instance.
        input_file_id: Input file ID.
        endpoint: API endpoint. Defaults to /v1/chat/completions.
                  Use /v1/chat/ds-test for test models.
                  Use /v1/embeddings for embedding models.
                  Use /v1/chat/completions for other models.
        completion_window: Completion window. Defaults to 24h.
    
    Returns:
        Batch job ID.
    """
    logger.info(f"Creating batch job from file ID...")
    batch = client.batches.create(
        input_file_id=input_file_id,
        endpoint=endpoint,
        completion_window=completion_window
    )
    logger.info(f"Batch job created, job ID: {batch.id}")
    return batch.id


def check_job_status(client: OpenAI, batch_id: str) -> str:
    """
    Check the batch job status.
    
    Args:
        client: OpenAI client instance.
        batch_id: Batch job ID.
    
    Returns:
        Job status.
    """
    batch = client.batches.retrieve(batch_id=batch_id)
    logger.info(f"Batch job status: {batch.status}")
    return batch.status


def cancel_batch_job(batch_id: str, client: Optional[OpenAI] = None) -> Dict:
    """
    Cancel a batch job.
    
    Args:
        batch_id: Batch job ID.
        client: OpenAI client instance. Created automatically if None.
    
    Returns:
        Job information after cancellation.
    """
    if client is None:
        client = get_openai_client()
    
    # Type assertion to ensure client is not None.
    assert client is not None, "Failed to create OpenAI client"
    
    logger.info(f"Cancelling batch job: {batch_id}")
    try:
        batch = client.batches.cancel(batch_id)
        logger.info(f"Batch job cancelled successfully")
        logger.info(f"Job ID: {batch.id}")
        logger.info(f"Job status: {batch.status}")
        return {
            "id": batch.id,
            "status": batch.status,
            "cancelled_at": getattr(batch, 'cancelled_at', None)
        }
    except Exception as e:
        logger.error(f"Failed to cancel batch job: {e}")
        raise


def wait_for_batch_completion(
    client: OpenAI,
    batch_id: str,
    check_interval: int = 10,
    timeout: Optional[int] = 3600
) -> Dict:
    """
    Wait for a batch job to complete.
    
    Args:
        client: OpenAI client instance.
        batch_id: Batch job ID.
        check_interval: Check interval in seconds. Defaults to 10 seconds.
        timeout: Timeout in seconds. Defaults to 3600 seconds (1 hour).
    
    Returns:
        Job status information dictionary.
    """
    start_time = time.time()
    check_count = 0
    last_status = None
    
    while True:
        check_count += 1
        elapsed_time = int(time.time() - start_time)
        
        batch = client.batches.retrieve(batch_id=batch_id)
        status = batch.status
        
        # Get additional information.
        request_counts = getattr(batch, 'request_counts', None)
        
        # Log when the status changes.
        if status != last_status:
            logger.info(f"Batch job status changed: {last_status or 'None'} -> {status}")
            last_status = status
        
        # Detailed log every 10 checks or on status changes.
        if check_count % 10 == 0 or status != last_status:
            status_msg = f"Batch job status: {status} (waited {elapsed_time}s, check #{check_count})"
            if request_counts:
                status_msg += f", request counts: {request_counts}"
            logger.info(status_msg)
        
        # Check final states.
        if status in ["completed", "failed", "expired", "cancelled"]:
            logger.info(f"Batch job finished, final status: {status}, elapsed time: {elapsed_time}s")
            return {
                "status": status,
                "batch_id": batch_id,
                "output_file_id": getattr(batch, 'output_file_id', None),
                "error_file_id": getattr(batch, 'error_file_id', None),
                "errors": getattr(batch, 'errors', None),
                "elapsed_time": elapsed_time,
                "request_counts": request_counts
            }
        
        # Check timeout.
        if timeout and elapsed_time > timeout:
            logger.warning(f"Batch job timed out ({timeout}s), current status: {status}")
            return {
                "status": "timeout",
                "batch_id": batch_id,
                "current_status": status,
                "elapsed_time": elapsed_time,
                "request_counts": request_counts
            }
        
        # Warn during long waits.
        if elapsed_time > 300 and elapsed_time % 60 == 0:  # Warn every 5 minutes.
            logger.warning(f"Batch job has waited {elapsed_time}s ({elapsed_time//60} minutes), status: {status}")
            if request_counts:
                logger.info(f"  Request counts: {request_counts}")
        
        time.sleep(check_interval)


def download_results(client: OpenAI, output_file_id: str, output_file_path: str) -> str:
    """
    Download successful request results from a batch job.
    
    Args:
        client: OpenAI client instance.
        output_file_id: Output file ID.
        output_file_path: File path for saving results.
    
    Returns:
        Result file path.
    """
    logger.info(f"Downloading successful batch request results...")
    content = client.files.content(output_file_id)
    
    # Save the result file locally.
    content.write_to_file(output_file_path)
    logger.info(f"Full output results saved to: {output_file_path}")
    return output_file_path


def download_errors(client: OpenAI, error_file_id: str, error_file_path: str) -> str:
    """
    Download failed request information from a batch job.
    
    Args:
        client: OpenAI client instance.
        error_file_id: Error file ID.
        error_file_path: File path for saving error information.
    
    Returns:
        Error file path.
    """
    logger.info(f"Downloading failed batch request information...")
    content = client.files.content(error_file_id)
    
    # Save the error information file locally.
    content.write_to_file(error_file_path)
    logger.info(f"Full failed request information saved to: {error_file_path}")
    return error_file_path


def prepare_batch_requests(
    requests_data: List[Dict],
    output_file: str = "batch_requests.jsonl"
) -> str:
    """
    Prepare batch request data and generate a JSONL file.
    
    Args:
        requests_data: Request data list. Each element is a dictionary
                      containing request parameters.
                      Format: [{"model": "qwen-plus", "messages": [...]}, ...]
        output_file: Output file path.
    
    Returns:
        Generated JSONL file path.
    """
    with open(output_file, 'w', encoding='utf-8') as f:
        for req in requests_data:
            json_line = json.dumps(req, ensure_ascii=False)
            f.write(json_line + '\n')
    
    logger.info(f"Generated batch request file: {output_file}, {len(requests_data)} requests total")
    return output_file


def parse_batch_results(result_file_path: str) -> List[Dict]:
    """
    Parse a batch job result file.
    
    Args:
        result_file_path: Result file path in JSONL format.
    
    Returns:
        Parsed result list. Each element contains a response field with
        body.choices[0].message.content.
    """
    results = []
    with open(result_file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            line = line.strip()
            if line:
                try:
                    result = json.loads(line)
                    # Batch usually returns:
                    # {"response": {"body": {"choices": [{"message": {"content": "..."}}]}}}
                    # or a direct response object.
                    results.append(result)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse result line {line_num}: {line[:100]}... error: {e}")
    
    logger.info(f"Parsing completed, {len(results)} results total")
    return results


def extract_content_from_batch_result(result: Dict) -> str:
    """
    Extract content from a batch result.
    
    Args:
        result: Result dictionary returned by batch.
    
    Returns:
        Extracted content string.
    """
    # Possible batch return formats:
    # 1. {"response": {"body": {"choices": [{"message": {"content": "..."}}]}}}
    # 2. {"response": {"body": {"choices": [{"message": {"content": "..."}}]}}, "custom_id": "..."}
    # 3. Directly contains a content field.
    
    if isinstance(result, dict):
        # Try to extract response.body.choices[0].message.content.
        if "response" in result:
            response = result["response"]
            if isinstance(response, dict) and "body" in response:
                body = response["body"]
                if isinstance(body, dict) and "choices" in body:
                    choices = body["choices"]
                    if isinstance(choices, list) and len(choices) > 0:
                        message = choices[0].get("message", {})
                        if isinstance(message, dict) and "content" in message:
                            return message["content"]
        
        # Try to get the content field directly.
        if "content" in result:
            return result["content"]
        
        # Try to get it directly from response.
        if "response" in result:
            response = result["response"]
            if isinstance(response, str):
                return response
    
    # If extraction fails, return the string representation.
    return json.dumps(result, ensure_ascii=False)


def batch_call(
    requests_data: List[Dict],
    model: str = "qwen-plus",
    input_file: Optional[str] = None,
    output_file: Optional[str] = None,
    error_file: Optional[str] = None,
    check_interval: int = 10,
    timeout: Optional[int] = 3600,
    endpoint: str = "/v1/chat/completions",
    keep_files: bool = False
) -> List[Dict]:
    """
    Complete workflow for batch API calls.
    
    Args:
        requests_data: Request data list. Each element is a dictionary.
                      Format: [{"model": "qwen-plus", "messages": [{"role": "user", "content": "..."}]}, ...]
        model: Model name. Defaults to qwen-plus.
        input_file: Input file path. Generated automatically if None.
        output_file: Output file path. Generated automatically if None.
        error_file: Error file path. Generated automatically if None.
        check_interval: Task status check interval in seconds.
        timeout: Timeout in seconds. None means no timeout.
        endpoint: API endpoint. Defaults to /v1/chat/completions.
        keep_files: Whether to keep intermediate files (input and result files).
    
    Returns:
        Parsed result list.
    """
    client = get_openai_client()
    
    # Prepare request data and convert it to the format required by the batch API.
    formatted_requests = []
    base_timestamp = int(time.time())
    for idx, req in enumerate(requests_data):
        # Use directly if already in batch format (contains method, url, and body).
        if "method" in req and "url" in req and "body" in req:
            formatted_req = req.copy()
            if "custom_id" not in formatted_req:
                formatted_req["custom_id"] = f"req_{base_timestamp}_{idx}"
            formatted_requests.append(formatted_req)
        else:
            # Convert to batch format.
            # Extract body content.
            body = {}
            if "body" in req:
                body = req["body"].copy()
            else:
                # Extract from the old format.
                body = {}
                if "model" in req:
                    body["model"] = req["model"]
                elif "model" not in body:
                    body["model"] = model
                if "messages" in req:
                    body["messages"] = req["messages"]
                if "temperature" in req:
                    body["temperature"] = req["temperature"]
                if "max_tokens" in req:
                    body["max_tokens"] = req["max_tokens"]
                # Copy other possible body fields.
                for key in req:
                    if key not in ["custom_id", "method", "url", "body"]:
                        if key not in body:
                            body[key] = req[key]
            
            # Build the batch-format request.
            formatted_req = {
                "custom_id": req.get("custom_id", f"req_{base_timestamp}_{idx}"),
                "method": req.get("method", "POST"),
                "url": req.get("url", endpoint),
                "body": body
            }
            formatted_requests.append(formatted_req)
    
    # Generate the input file.
    if input_file is None:
        input_file = f"batch_input_{int(time.time())}.jsonl"
    
    prepare_batch_requests(formatted_requests, input_file)
    
    try:
        # Step 1: Upload the file.
        input_file_id = upload_file(client, input_file)
        
        # Step 2: Create the batch job.
        batch_id = create_batch_job(client, input_file_id, endpoint=endpoint)
        
        # Step 3: Wait for the job to complete.
        logger.info("Waiting for batch job to complete...")
        status_info = wait_for_batch_completion(
            client, batch_id, check_interval, timeout
        )
        
        if status_info["status"] == "failed":
            error_msg = status_info.get("errors", "unknown error")
            logger.error(f"Batch job failed: {error_msg}")
            raise Exception(f"Batch job failed: {error_msg}")
        
        if status_info["status"] != "completed":
            logger.error(f"Batch job did not complete successfully, status: {status_info['status']}")
            return []
        
        # Step 4: Download the result file.
        results = []
        
        output_file_id = status_info.get("output_file_id")
        if output_file_id:
            if output_file is None:
                output_file = f"batch_results_{int(time.time())}.jsonl"
            
            download_results(client, output_file_id, output_file)
            results = parse_batch_results(output_file)
        
        # Download the error file if present.
        error_file_id = status_info.get("error_file_id")
        if error_file_id:
            if error_file is None:
                error_file = f"batch_errors_{int(time.time())}.jsonl"
            
            download_errors(client, error_file_id, error_file)
            logger.warning(f"Some requests failed, error information saved to: {error_file}")
        
        # Clean up temporary files.
        if not keep_files:
            try:
                if os.path.exists(input_file):
                    os.remove(input_file)
                    logger.info(f"Deleted temporary input file: {input_file}")
                if output_file and os.path.exists(output_file) and not keep_files:
                    # The result file can be retained; by default this branch does nothing.
                    pass
            except Exception as e:
                logger.warning(f"Failed to delete temporary files: {e}")
        
        return results
        
    except Exception as e:
        logger.error(f"Batch call failed: {e}")
        raise
    finally:
        # Clean up temporary files.
        if not keep_files and input_file and os.path.exists(input_file):
            try:
                os.remove(input_file)
            except:
                pass


# Convenience function: generate batch requests from a prompt list.
def batch_call_from_prompts(
    prompts: List[str],
    model: str = "qwen-plus",
    system_prompt: str = "You are a helpful assistant.",
    **kwargs
) -> List[Dict]:
    """
    Generate batch requests from a prompt list and execute them.
    
    Args:
        prompts: Prompt string list.
        model: Model name.
        system_prompt: System prompt.
        **kwargs: Other parameters passed to batch_call.
    
    Returns:
        Parsed result list.
    """
    requests_data = []
    base_timestamp = int(time.time())
    endpoint = kwargs.get("endpoint", "/v1/chat/completions")
    
    for idx, prompt in enumerate(prompts):
        # Use the format required by the batch API.
        requests_data.append({
            "custom_id": f"prompt_{base_timestamp}_{idx}",
            "method": "POST",
            "url": endpoint,
            "body": {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ]
            }
        })
    
    return batch_call(requests_data, model=model, **kwargs)


# Convenience function: generate batch requests from API classification requests.
def batch_classify_apis(
    api_list: List[Dict[str, str]],
    classification_prompt_template: str,
    model: str = "qwen-plus",
    **kwargs
) -> List[Dict]:
    """
    Classify APIs in batch.
    
    Args:
        api_list: API list. Each element contains api_name and api_summary.
                  Format: [{"api_name": "...", "api_summary": "..."}, ...]
        classification_prompt_template: Classification prompt template using {} placeholders.
        model: Model name.
        **kwargs: Other parameters passed to batch_call.
    
    Returns:
        Parsed result list. Each element contains the extracted content string.
    """
    prompts = []
    for api_info in api_list:
        prompt = classification_prompt_template.format(
            api_info["api_name"],
            api_info["api_summary"]
        )
        prompts.append(prompt)
    
    results = batch_call_from_prompts(prompts, model=model, **kwargs)
    
    # Extract content.
    extracted_results = []
    for result in results:
        if isinstance(result, dict):
            content = extract_content_from_batch_result(result)
            extracted_results.append({"content": content, "raw": result})
        else:
            extracted_results.append({"content": str(result), "raw": result})
    
    return extracted_results


def list_batch_jobs(
    client: Optional[OpenAI] = None,
    after: Optional[str] = None,
    limit: Optional[int] = None,
    status: Optional[str] = None,
    input_file_ids: Optional[str] = None,
    ds_name: Optional[str] = None,
    create_after: Optional[str] = None,
    create_before: Optional[str] = None
) -> List[Dict]:
    """
    Query the batch job list.
    
    Args:
        client: OpenAI client instance. Created automatically if None.
        after: Last batch job ID from the previous page, used for pagination.
        limit: Maximum number of jobs to return.
        status: Job status filter, comma-separated, e.g. "completed,expired".
        input_file_ids: Input file ID filter, comma-separated.
        ds_name: Job name filter.
        create_after: Creation time filter start, format: YYYYMMDDHHmmss.
        create_before: Creation time filter end, format: YYYYMMDDHHmmss.
    
    Returns:
        Batch job list. Each element contains detailed job information.
    """
    if client is None:
        client = get_openai_client()
    
    assert client is not None, "Failed to create OpenAI client"
    
    try:
        # Build extra_query parameters.
        extra_query = {}
        if ds_name:
            extra_query['ds_name'] = ds_name
        if input_file_ids:
            extra_query['input_file_ids'] = input_file_ids
        if status:
            extra_query['status'] = status
        if create_after:
            extra_query['create_after'] = create_after
        if create_before:
            extra_query['create_before'] = create_before
        
        # Call the API.
        batches = client.batches.list(
            after=after,
            limit=limit,
            extra_query=extra_query if extra_query else None
        )
        
        # Convert to a list of dictionaries.
        batch_list = []
        if batches.data is None:
            logger.info("No matching batch jobs found")
            return batch_list
        
        for batch in batches.data:
            batch_info = {
                "id": batch.id,
                "status": batch.status,
                "created_at": getattr(batch, 'created_at', None),
                "ended_at": getattr(batch, 'ended_at', None),
                "input_file_id": getattr(batch, 'input_file_id', None),
                "output_file_id": getattr(batch, 'output_file_id', None),
                "error_file_id": getattr(batch, 'error_file_id', None),
            }
            
            # Add request counts.
            if hasattr(batch, 'request_counts'):
                counts = batch.request_counts
                batch_info["request_counts"] = {
                    "total": counts.total if hasattr(counts, 'total') else None,
                    "completed": counts.completed if hasattr(counts, 'completed') else None,
                    "failed": counts.failed if hasattr(counts, 'failed') else None,
                }
            
            batch_list.append(batch_info)
        
        logger.info(f"Found {len(batch_list)} batch jobs")
        return batch_list
        
    except Exception as e:
        logger.error(f"Failed to query batch job list: {e}")
        raise


def query_batch_status(batch_id: str, client: Optional[OpenAI] = None) -> Dict:
    """
    Query detailed information for a batch job.
    
    Args:
        batch_id: Batch job ID.
        client: OpenAI client instance. Created automatically if None.
    
    Returns:
        Dictionary containing detailed job information.
    """
    if client is None:
        client = get_openai_client()
    
    # Type check: ensure client is not None.
    assert client is not None, "Failed to create OpenAI client"
    
    try:
        batch = client.batches.retrieve(batch_id=batch_id)
        
        info = {
            "batch_id": batch_id,
            "status": batch.status,
            "created_at": getattr(batch, 'created_at', None),
            "in_progress_at": getattr(batch, 'in_progress_at', None),
            "completed_at": getattr(batch, 'completed_at', None),
            "failed_at": getattr(batch, 'failed_at', None),
            "expired_at": getattr(batch, 'expired_at', None),
            "cancelled_at": getattr(batch, 'cancelled_at', None),
            "request_counts": getattr(batch, 'request_counts', None),
            "output_file_id": getattr(batch, 'output_file_id', None),
            "error_file_id": getattr(batch, 'error_file_id', None),
            "errors": getattr(batch, 'errors', None),
            "metadata": getattr(batch, 'metadata', None),
        }
        
        return info
    except Exception as e:
        logger.error(f"Failed to query batch job status: {e}")
        raise


def print_batch_status(batch_id: str, client: Optional[OpenAI] = None):
    """
    Print detailed information for a batch job.
    
    Args:
        batch_id: Batch job ID.
        client: OpenAI client instance. Created automatically if None.
    """
    info = query_batch_status(batch_id, client)
    
    print(f"\n{'='*80}")
    print(f"Batch job details")
    print(f"{'='*80}")
    print(f"Job ID: {info['batch_id']}")
    print(f"Status: {info['status']}")
    
    if info['created_at']:
        print(f"Created at: {info['created_at']}")
    if info['in_progress_at']:
        print(f"Started at: {info['in_progress_at']}")
    if info['completed_at']:
        print(f"Completed at: {info['completed_at']}")
    if info['failed_at']:
        print(f"Failed at: {info['failed_at']}")
    if info['expired_at']:
        print(f"Expired at: {info['expired_at']}")
    if info['cancelled_at']:
        print(f"Cancelled at: {info['cancelled_at']}")
    
    if info['request_counts']:
        print(f"\nRequest counts:")
        if isinstance(info['request_counts'], dict):
            for key, value in info['request_counts'].items():
                print(f"  {key}: {value}")
        else:
            print(f"  {info['request_counts']}")
    
    if info['output_file_id']:
        print(f"\nOutput file ID: {info['output_file_id']}")
    if info['error_file_id']:
        print(f"Error file ID: {info['error_file_id']}")
    
    if info['errors']:
        print(f"\nError information:")
        if isinstance(info['errors'], dict) and 'data' in info['errors']:
            errors = info['errors']['data']
            print(f"  Error count: {len(errors)}")
            for i, error in enumerate(errors[:5], 1):  # Show only the first 5 errors.
                print(f"  Error {i}: {error}")
            if len(errors) > 5:
                print(f"  ... {len(errors) - 5} more errors")
        else:
            print(f"  {info['errors']}")
    
    if info['metadata']:
        print(f"\nMetadata: {info['metadata']}")
    
    print(f"{'='*80}\n")
