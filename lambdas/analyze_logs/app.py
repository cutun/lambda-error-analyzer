# lambda_error_analyzer/lambdas/analyze_logs/app.py
import json
import uuid
import boto3
import os
import time
import urllib.parse
import gzip
from typing import Dict, Any, List
from datetime import datetime, timedelta, timezone

# Import helper classes and models from other files in the same directory
from clusterer import LogClusterer
from bedrock_summarizer import BedrockSummarizer


# initialize all clients and load config outside of handler which will allows them to reused warm Lambda invocations
try:
    S3_CLIENT = boto3.client('s3')
    DYNAMODB_RESOURCE = boto3.resource('dynamodb', region_name=os.environ['AWS_REGION'])
    DYNAMODB_TABLE = DYNAMODB_RESOURCE.Table(os.environ["DYNAMODB_TABLE_NAME"])
except KeyError as e:
    # This will cause a Lambda init failure, which is appropriate for missing config.
    print(f"FATAL: Missing required environment variable: {e}")
    S3_CLIENT = None
    DYNAMODB_RESOURCE = None
    DYNAMODB_TABLE = None
    raise e

_DEFAULT_LOG_PATTERN = r"ERROR:\s+.*,CRITICAL:\s+.*"
LOG_PATTERNS = os.environ.get('LOG_PATTERNS', _DEFAULT_LOG_PATTERN).split(',')


def get_logs_from_s3(bucket: str, key: str) -> List[str]:
    """
    Downloads a log file from S3, decompresses it if necessary, and splits it
    into a list of individual log entries.
    """
    try:
        # Get key from S3 events
        decoded_key = urllib.parse.unquote_plus(key)
        response = S3_CLIENT.get_object(Bucket=bucket, Key=decoded_key)
        
        file_content = response["Body"].read()

        # We must decompress due to Kinesis Firehose is configured to gzip files.
        if decoded_key.endswith(".gz"):
            file_content = gzip.decompress(file_content)

        # Decode from bytes to string and split into lines
        log_string = file_content.decode("utf-8")
        
        # making sure handle logs where logs are separated by single or double newlines.
        return log_string.replace('\n\n', '\n').strip().split('\n')

    except Exception as e:
        print(f"Error getting logs from S3 bucket '{bucket}', key '{decoded_key}': {e}")
        return []


def persist_analysis_to_dynamodb(analysis_result: dict):
    """
    Saves the final analysis result dictionary to DynamoDB.
    """
    try:
        # The analysis_result is already a dictionary, ready for DynamoDB
        DYNAMODB_TABLE.put_item(Item=analysis_result)
        print(f"Successfully saved analysis {analysis_result['analysis_id']} to DynamoDB.")
        # Optional: Print the saved data for debugging in CloudWatch
        # print(f"Saved Analysis: {json.dumps(analysis_result)}")
    except Exception as e:
        print(f"Error saving to DynamoDB: {e}")
        # In a real app, you might re-raise the exception or send to a DLQ
        raise e


def process_log_batch(raw_log_batch):
    # Cluster the logs Here (First step)
    clusterer = LogClusterer(patterns=LOG_PATTERNS)
    log_clusters = clusterer.cluster_logs(raw_log_batch)

    # Summarize the clusters using Bedrock (Second step)
    summarizer = BedrockSummarizer()
    summary_text = summarizer.summarize_clusters(log_clusters)

    # Assemble the final analysis result object (Third Step)
    # Currently we are using dictionary here, but in the future switching to dataclass would be a lot cleaner.
    analysis_result = {
        "analysis_id": str(uuid.uuid4()),
        "summary": summary_text,
        "total_logs_processed": len(raw_log_batch),
        "total_clusters_found": len(log_clusters),
        "clusters": log_clusters, # Currently it is assuming cluster_logs return a lists of dict so make sure double check when you switching the output of cluster_log
        "processed_at": datetime.now(timezone.utc).isoformat(),
        # Set a Time-to-Live (TTL) for auto-deletion from DynamoDB after 48 hours
        "ttl_expiry": int((datetime.now(timezone.utc) + timedelta(hours=48)).timestamp()),
    }
    
    # Persist the result to DynamoDB (Fourth Step)
    persist_analysis_to_dynamodb(analysis_result)
    return analysis_result
        


def handler(event: Dict[str, Any], context: object) -> Dict[str, Any]:
    """
    Main Lambda handler, triggered by an S3 event.
    """
    print(f"Received event: {json.dumps(event)}")
    
    try:
        s3_record = event['Records'][0]['s3']
        bucket = s3_record['bucket']['name']
        key = s3_record['object']['key']
    except (KeyError, IndexError):
        print("WARNING: Not a valid S3 event. No action taken.")
        return {"statusCode": 200, "body": json.dumps("No S3 event detected.")}

    print(f"Processing file: s3://{bucket}/{key}")
    raw_logs = get_logs_from_s3(bucket, key)

    results = []

    batch_size = 10000  # tested reasonable upper limit
    total_lines = len(raw_logs)
    # Ceiling division to calculate the total number of batches
    num_batches = (total_lines + batch_size - 1) // batch_size
    for i in range(num_batches):
        start_index = i * batch_size
        end_index = start_index + batch_size
        batch_lines = raw_logs[start_index:end_index]
        analysis_result = process_log_batch(batch_lines)
        results.append(analysis_result)
        time.sleep(1) # Avoid spamming api calls

    if not raw_logs:
        print("Log file was empty or could not be read. Exiting.")
        return {"statusCode": 200, "body": json.dumps("Log file empty.")}


    # Return a success response (Fifth Step)
    return {
        "statusCode": 200,
        "body": json.dumps({"result": results}, indent=2)
    }
