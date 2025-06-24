# lambda_error_analyzer/lambdas/analyze_logs/app.py
import json
import uuid
import boto3
import os
import urllib.parse
from typing import Dict, Any, List
from datetime import datetime, timedelta

# Import helper classes and models from other files in this directory
from models import LogAnalysisResult, get_settings
from clusterer import LogClusterer
from bedrock_summarizer import BedrockSummarizer

# --- Initialize S3 client outside the handler for reuse ---
s3_client = boto3.client('s3')

def get_logs_from_s3(bucket: str, key: str) -> List[str]:
    """Downloads a log file from S3 and splits it into a list of logs."""
    try:
        # URL-decode the key in case it has special characters (e.g., spaces)
        key = urllib.parse.unquote_plus(key)
        response = s3_client.get_object(Bucket=bucket, Key=key)
        # Read the file content and decode it from bytes to a string
        log_content = response['Body'].read().decode('utf-8')
        # Split logs by double newline, which is how our sample file is formatted.
        # This might need to be adjusted based on the actual log format.
        return log_content.strip().split('\n\n')
    except Exception as e:
        print(f"Error getting logs from S3 bucket '{bucket}', key '{key}': {e}")
        # Return an empty list to prevent the Lambda from crashing
        return []


def handler(event: Dict[str, Any], context: object) -> Dict[str, Any]:
    """
    Main Lambda handler function.
    This version is triggered by an S3 event and reads configuration from
    environment variables.
    """
    print(f"Received event: {json.dumps(event)}")
    
    # --- DYNAMIC DATA: Get raw logs from the S3 trigger event ---
    try:
        # S3 events contain a 'Records' list
        s3_record = event['Records'][0]['s3']
        bucket = s3_record['bucket']['name']
        key = s3_record['object']['key']
        
        print(f"Processing file: s3://{bucket}/{key}")
        raw_logs = get_logs_from_s3(bucket, key)

    except (KeyError, IndexError):
        # This happens if the event is not a valid S3 trigger (e.g., a test from the console)
        print("WARNING: Not a valid S3 event. No logs to process.")
        # We can return a success message as there's no work to do.
        return {"statusCode": 200, "body": json.dumps("No S3 event detected.")}

    if not raw_logs:
        print("Log file was empty or could not be read. Exiting.")
        return {"statusCode": 200, "body": json.dumps("Log file empty.")}

    # --- DYNAMIC CONFIGURATION: Load regex patterns from an environment variable ---
    # The value should be a comma-separated string, e.g., "ERROR: .*,CRITICAL: .*"
    patterns_str = os.environ.get('LOG_PATTERNS', r"ERROR:\s+.*,CRITICAL:\s+.*")
    log_patterns = patterns_str.split(',')
    
    # 1. Cluster the logs
    clusterer = LogClusterer(patterns=log_patterns)
    log_clusters = clusterer.cluster_logs(raw_logs)

    # 2. Summarize the clusters using Bedrock
    summarizer = BedrockSummarizer()
    summary_text = summarizer.summarize_clusters(log_clusters)

    # 3. Assemble the final analysis result object
    analysis_result = LogAnalysisResult(
        analysis_id=str(uuid.uuid4()),
        summary=summary_text,
        total_logs_processed=len(raw_logs),
        total_clusters_found=len(log_clusters),
        clusters=log_clusters,
        ttl_expiry=int((datetime.now() + timedelta(hours=48)).timestamp())
    )
    
    # 4. Persist the result to DynamoDB
    try:
        settings = get_settings()
        dynamodb = boto3.resource('dynamodb', region_name=settings.aws_region)
        table = dynamodb.Table(settings.dynamodb_table_name)
        
        analysis_dict = analysis_result.model_dump(mode='json')
        table.put_item(Item=analysis_dict)
        print(f"Successfully saved analysis {analysis_result.analysis_id} to DynamoDB.")

    except Exception as e:
        print(f"Error saving to DynamoDB: {e}")
        # In a real app, you might want to re-raise the exception or send an alert
        
    # The final JSON output is returned by the Lambda
    return {
        "statusCode": 200,
        "body": analysis_result.model_dump_json(indent=2)
    }