# lambda/filter_alert/app.py
import os
import json
import boto3

# Import lambda-specific modules
from alert_stats import AlertFilter
from db_history import get_batch_historical_timestamps, batch_update_history, unmarshall_dynamodb_item


# Initialize AWS clients used by this specific lambda.
try:
    SNS_CLIENT = boto3.client('sns')
    FINAL_ALERTS_TOPIC_ARN = os.environ['FINAL_ALERTS_TOPIC_ARN']
except KeyError as e:
    print(f"FATAL: Missing required environment variable: {e}")
    SNS_CLIENT = None
    FINAL_ALERTS_TOPIC_ARN = None
    raise e

# Main logic and handler
def filter_actionable_clusters(analysis_result: dict) -> list[dict]:
    """
    Efficiently filters clusters by batching all database read and write operations.
    """
    clusters = analysis_result.get("clusters", [])
    if not clusters:
        return []

    # Step 1: Batch Read
    # Collect all unique signatures and fetch their histories in one go.
    unique_signatures = list(set(c['signature'] for c in clusters if c.get('signature')))
    all_historical_data = get_batch_historical_timestamps(unique_signatures)

    # Step 2: In-Memory Filtering
    actionable_clusters = []
    history_items_to_write = []
    alert_filter = AlertFilter()

    for cluster in clusters:
        stripped_cluster = dict()
        signature = cluster.get("signature")
        if not signature:
            continue
        
        # Get pre-fetched history for this specific signature
        historical_timestamps = all_historical_data.get(signature, [])
        current_event_timestamps = cluster.get("timestamps", [])

        # Add the new timestamps to the list that will be batch written to the DB
        for ts in current_event_timestamps:
            history_items_to_write.append({'signature': signature, 'timestamp': ts})

        # Decide whether to alert for this cluster
        decision = alert_filter.should_alert(
            historical_timestamps=historical_timestamps,
            current_event_timestamps=current_event_timestamps
        )

        print(f" -> Filter Decision for '{signature[:50]}...': {'Alert' if decision else 'Suppress'}. Reason: {decision.reason}")

        if decision:
            # Use a stripped down cluster to minimize used bandwith over SNS
            stripped_cluster["signature"] = cluster.get("signature", "")
            stripped_cluster["count"] = cluster.get("count", 0)
            stripped_cluster["representative_log"] = cluster.get("representative_log", "N/A")
            actionable_clusters.append(stripped_cluster)
    
    # Step 3: Batch Write
    # After processing all clusters, write all the new history items in one batch.
    if history_items_to_write:
        batch_update_history(history_items_to_write)

    # Sort the final list of actionable clusters by importance
    actionable_clusters.sort(reverse=True, key=lambda c: c.get("level_rank", 1) * c.get("count", 1))

    return actionable_clusters

def process_record(record: dict):
    """
    Processes a single record from the DynamoDB stream.
    """
    try:
        if record.get('eventName') != 'INSERT':
            print(" -> Skipping record (not an INSERT event).")
            return

        new_image = record.get('dynamodb', {}).get('NewImage')
        if not new_image:
            print(" -> Skipping record (no 'NewImage' data).")
            return
        
        analysis_result = unmarshall_dynamodb_item(new_image)
        print(f" -> Successfully parsed analysis for ID: {analysis_result.get('analysis_id')}")

        actionable_clusters = filter_actionable_clusters(analysis_result)

        if actionable_clusters:
            analysis_result["clusters"] = actionable_clusters
            analysis_result["total_clusters_found"] = len(actionable_clusters)
            analysis_result["total_logs_processed"] = sum(c.get("count", 0) for c in actionable_clusters)
            
            print(f" -> ✅ Filter PASSED with {len(actionable_clusters)} clusters. Publishing to SNS.")

            SNS_CLIENT.publish(
                TopicArn=FINAL_ALERTS_TOPIC_ARN,
                Message=json.dumps(analysis_result, default=str),
                Subject="Action Required: Anomalous Error Patterns Detected"
            )
        else:
            print(" -> ℹ️ All clusters filtered. No actionable clusters found. Suppressing notification.")
    
    except Exception as e:
        print(f" -> ❌ An unexpected error occurred while processing record: {e}")

def handler(event, context):
    """
    Triggered by a DynamoDB Stream. It intelligently filters the analysis result
    and publishes to SNS if any actionable alerts remain.
    """
    print("--- FilterAlert Lambda Triggered ---")
    if not all([SNS_CLIENT, FINAL_ALERTS_TOPIC_ARN]):
        print("FATAL: Lambda is not configured correctly. Aborting.")
        return {"statusCode": 500, "body": "Configuration error."}
    
    for i, record in enumerate(event.get('Records', [])):
        print(f"\n--- Processing Record #{i+1} ---")
        process_record(record)

    return {"statusCode": 200, "body": "Filter process complete."}
