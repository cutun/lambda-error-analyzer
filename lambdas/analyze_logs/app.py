# lambda_error_analyzer/lambdas/analyze_logs/app.py
import json
import uuid
import boto3
import os
import urllib.parse
from typing import Dict, Any, List
from decimal import Decimal # --- NEW: Import the Decimal type ---

# Import helper classes and models
from .models import LogAnalysisResult, get_settings
from .clusterer import LogClusterer
from .bedrock_summarizer import BedrockSummarizer
from .detector import PatternDetector

s3_client = boto3.client('s3')

def get_logs_from_s3(bucket: str, key: str) -> List[str]:
    """Downloads a log file from S3 and splits it into a list of logs."""
    try:
        key = urllib.parse.unquote_plus(key)
        response = s3_client.get_object(Bucket=bucket, Key=key)
        log_content = response['Body'].read().decode('utf-8')
        return log_content.strip().split('\n\n')
    except Exception as e:
        print(f"Error getting logs from S3 bucket '{bucket}', key '{key}': {e}")
        return []

def floats_to_decimals(obj: Any) -> Any:
    """
    Recursively walks a data structure and converts all float values to
    Decimal objects, which are required by DynamoDB.
    """
    if isinstance(obj, list):
        return [floats_to_decimals(v) for v in obj]
    elif isinstance(obj, dict):
        return {k: floats_to_decimals(v) for k, v in obj.items()}
    elif isinstance(obj, float):
        # Convert float to string before converting to Decimal to avoid precision issues
        return Decimal(str(obj))
    return obj

def handler(event: Dict[str, Any], context: object) -> Dict[str, Any]:
    """Main Lambda handler function, now with recurrence and anomaly detection."""
    print(f"Received event: {json.dumps(event)}")
    
    try:
        s3_record = event['Records'][0]['s3']
        bucket = s3_record['bucket']['name']
        key = s3_record['object']['key']
        print(f"Processing file: s3://{bucket}/{key}")
        raw_logs = get_logs_from_s3(bucket, key)
    except (KeyError, IndexError):
        print("WARNING: Not a valid S3 event. Using hardcoded logs for local testing.")
        # Fallback to hardcoded logs if not a real S3 event
        raw_logs = [
            "2024-06-17T13:31:00Z [ERROR] Authentication failed for user 'jane.doe'. Error: Invalid credentials.",
            "2024-06-17T13:32:00Z [CRITICAL] Core component 'BillingService' has failed.",
            "2024-06-17T13:34:00Z [ERROR] Authentication failed for user 'john.doe'. Error: Invalid credentials.",
            "2024-06-17T13:35:00Z [CRITICAL] Core component 'BillingService' has failed.",
            "2024-06-17T14:00:00Z [WARNING] Disk space is running low on /dev/sda1."
        ]

    if not raw_logs:
        print("Log file was empty or could not be read. Exiting.")
        return {"statusCode": 200, "body": json.dumps("Log file empty.")}

    patterns_str = os.environ.get('LOG_PATTERNS', r"Error:\s+.*,CRITICAL:\s+.*")
    log_patterns = patterns_str.split(',')
    
    clusterer = LogClusterer(patterns=log_patterns)
    log_clusters = clusterer.cluster_logs(raw_logs)

    if log_clusters:
        detector = PatternDetector()
        detector.analyze_patterns(log_clusters)

    summarizer = BedrockSummarizer()
    summary_text = summarizer.summarize_clusters(log_clusters)

    analysis_result = LogAnalysisResult(
        analysis_id=str(uuid.uuid4()),
        summary=summary_text,
        total_logs_processed=len(raw_logs),
        total_clusters_found=len(log_clusters),
        clusters=log_clusters
    )
    
    # --- FIX: Convert floats to Decimals before saving to DynamoDB ---
    try:
        settings = get_settings()
        dynamodb = boto3.resource('dynamodb', region_name=settings.aws_region)
        table = dynamodb.Table(settings.dynamodb_table_name)
        
        # First, dump the model to a standard python dict
        analysis_dict = analysis_result.model_dump(mode='json')
        
        # Convert all float values in the dict to Decimal objects
        item_for_dynamo = floats_to_decimals(analysis_dict)
        
        table.put_item(Item=item_for_dynamo)
        print(f"Successfully saved analysis {analysis_result.analysis_id} to DynamoDB.")
    except Exception as e:
        print(f"Error saving analysis result to DynamoDB: {e}")
        
    return {
        "statusCode": 200,
        "body": analysis_result.model_dump_json(indent=2)
    }
