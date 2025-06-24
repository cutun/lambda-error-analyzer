# lambda_error_analyzer/lambdas/analyze_logs/app.py
import json
import uuid
import boto3
from typing import Dict, Any

# Import helper classes and models from other files in this directory
from .models import LogAnalysisResult, get_settings
from .clusterer import LogClusterer
from .bedrock_summarizer import BedrockSummarizer

# --- Configuration ---
LOG_PATTERNS = [
    r"ERROR:\s+.*",
    r"CRITICAL:\s+.*"
]

def handler(event: Dict[str, Any], context: object) -> Dict[str, Any]:
    """
    Main Lambda handler function.
    """
    print(f"Received event: {json.dumps(event)}")
    
    # For demonstration, we'll use a hardcoded list of logs.
    raw_logs = [
        "2024-06-17T13:30:00Z [INFO] Service started successfully.",
        "2024-06-17T13:31:00Z [ERROR] Authentication failed for user 'jane.doe'. Error: Invalid credentials.",
        "2024-06-17T13:32:00Z [CRITICAL] Core component 'BillingService' has failed.",
        "2024-06-17T13:33:00Z [DEBUG] A-OK.",
        "2024-06-17T13:34:00Z [ERROR] Authentication failed for user 'john.doe'. Error: Invalid credentials.",
        "2024-06-17T13:35:00Z [CRITICAL] Core component 'BillingService' has failed.",
        "2024-06-17T14:00:00Z [WARNING] Disk space is running low on /dev/sda1."
    ]

    # 1. Cluster the logs
    clusterer = LogClusterer(patterns=LOG_PATTERNS)
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
        clusters=log_clusters
    )
    
    # 4. Persist the result to DynamoDB
    try:
        settings = get_settings()
        dynamodb = boto3.resource('dynamodb', region_name=settings.aws_region)
        table = dynamodb.Table(settings.dynamodb_table_name)
        
        # --- FIX: Use model_dump(mode='json') to ensure datetimes are serialized to strings ---
        # This matches the 'S' (String) type defined for 'processed_at' in our GSI.
        analysis_dict = analysis_result.model_dump(mode='json')
        
        table.put_item(Item=analysis_dict)
        print(f"Successfully saved analysis {analysis_result.analysis_id} to DynamoDB.")

    except Exception as e:
        print(f"Error saving to DynamoDB: {e}")
        
    # The final JSON output is returned by the Lambda
    return {
        "statusCode": 200,
        "body": analysis_result.model_dump_json(indent=2)
    }
