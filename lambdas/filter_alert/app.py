import os
import json
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer
from datetime import datetime, timezone, timedelta

# --- Import your custom AlertFilter class from the common layer ---
from alert_stats import AlertFilter

# ==========================================================
# ================== DynamoDB Functions ====================
# ==========================================================

# Initialize DynamoDB client and table resource outside the handler for reuse
# This is safe because Lambda can reuse this execution environment.
try:
    dynamodb = boto3.resource('dynamodb')
    history_table = dynamodb.Table(os.environ['HISTORY_TABLE_NAME'])
except KeyError:
    print("FATAL: HISTORY_TABLE_NAME environment variable not set.")
    # In a real scenario, you might have better error handling, but for Lambda this will cause an init failure.
    history_table = None

def unmarshall_dynamodb_item(ddb_item: dict) -> dict:
    """Converts a DynamoDB-formatted item into a regular Python dictionary."""
    class CustomDeserializer(TypeDeserializer):
        def _deserialize_n(self, value):
            return int(value)
    deserializer = CustomDeserializer()
    return {k: deserializer.deserialize(v) for k, v in ddb_item.items()}

def get_historical_data_for_cluster(signature: str) -> list:
    """
    Queries DynamoDB to get the 48-hour history for a specific error signature.
    """
    if not history_table:
        print("  -> ❌ DynamoDB history table not initialized. Cannot fetch history.")
        return []
        
    print(f"  -> Fetching 48hr history for signature: '{signature[:50]}...'")
    try:
        response = history_table.query(
            KeyConditionExpression='signature = :sig',
            ExpressionAttributeValues={':sig': signature},
            ScanIndexForward=False # Get newest items first, though we sort later
        )
        items = response.get('Items', [])
        print(f"  -> Found {len(items)} historical records.")
        return [item['timestamp'] for item in items]
    except ClientError as e:
        print(f"  -> ❌ DynamoDB query failed: {e.response['Error']['Message']}")
        return []

def update_history_with_individual_events(signature: str, timestamps: list[str]):
    """
    Writes each individual log event to the history table.
    """
    if not history_table:
        print("  -> ❌ DynamoDB history table not initialized. Cannot write history.")
        return
        
    print(f"  -> Writing {len(timestamps)} individual events to history for signature: '{signature[:50]}...'")
    try:
        # Use DynamoDB's batch_writer for efficient bulk writes
        with history_table.batch_writer() as batch:
            for ts in timestamps:
                # DynamoDB TTL requires the timestamp to be a Unix epoch in seconds.
                ttl_timestamp = int((datetime.now(timezone.utc) + timedelta(hours=48)).timestamp())

                batch.put_item(
                    Item={
                        'signature': signature,
                        'timestamp': ts, # Use the individual timestamp as the sort key
                        'ttl': ttl_timestamp
                    }
                )
        print(f"  -> ✅ Successfully updated history with {len(timestamps)} events.")
    except ClientError as e:
        print(f"  -> ❌ DynamoDB batch_writer failed: {e.response['Error']['Message']}")


# ==========================================================
# ================ Main Lambda Handler =====================
# ==========================================================

def filter_alert(analysis_result):
    """
    The intelligent filter function. It iterates through clusters, fetches their history,
    uses the AlertFilter class, and updates the history table with individual events.
    """
    actionable_clusters = []
    
    for cluster in analysis_result.get("clusters", []):
        signature = cluster.get("signature")
        current_count = cluster.get("count")
        
        if not signature or current_count is None:
            continue

        # 1. Fetch the 48-hour history for this specific cluster signature.
        # This history will be a list of individual events (count=1).
        historical_data = get_historical_data_for_cluster(signature)
        
        # 2. Call the intelligent filter to make a decision on the new batch.
        if AlertFilter.should_alert(historical_data):
            actionable_clusters.append(cluster)
        
        # 3. IMPORTANT: Update the history table with each individual timestamp from this batch.
        # This provides a granular history for future analyses.
        cluster_timestamps = cluster.get("timestamps", [])
        if cluster_timestamps:
            update_history_with_individual_events(signature, cluster_timestamps)

    # Rebuild the result object with only the actionable clusters
    analysis_result["clusters"] = actionable_clusters
    analysis_result["total_logs_processed"] = sum(c["count"] for c in analysis_result.get("clusters", []))
    analysis_result["total_clusters_found"] = len(analysis_result.get("clusters", []))
    return analysis_result


def handler(event, context):
    """
    This handler is triggered by a DynamoDB Stream, intelligently filters the result
    using the AlertFilter class, and publishes to SNS if actionable alerts remain.
    """
    print("--- FilterAlert Lambda Triggered ---")
    sns = boto3.client('sns')
    
    try:
        final_alerts_topic_arn = os.environ['FINAL_ALERTS_TOPIC_ARN']
    except KeyError:
        print("FATAL: FINAL_ALERTS_TOPIC_ARN environment variable not set.")
        return {"statusCode": 500, "body": "Configuration error."}

    for i, record in enumerate(event.get('Records', [])):
        print(f"\n--- Processing Record #{i+1} ---")
        try:
            if record.get('eventName') != 'INSERT':
                print(f"  -> Skipping record (not an INSERT event).")
                continue

            new_image = record.get('dynamodb', {}).get('NewImage')
            if not new_image:
                print("  -> Skipping record (no 'NewImage' data).")
                continue

            analysis_result = unmarshall_dynamodb_item(new_image)
            print("  -> Successfully parsed analysis result from stream.")

            filtered_result = filter_alert(analysis_result)

            if filtered_result.get("clusters"):
                print(f"  -> Filter PASSED. Publishing to SNS topic: {final_alerts_topic_arn}")
                sns.publish(
                    TopicArn=final_alerts_topic_arn,
                    Message=json.dumps(filtered_result, default=str),
                    Subject="Action Required: Anomalous Error Patterns Detected"
                )
                print("  -> ✅ Filtered alert successfully published to SNS.")
                print(f"  -> Output: {filtered_result}")
            else:
                print("  -> ℹ️ Filter FAILED. No actionable clusters found. No alert sent.")
        
        except Exception as e:
            print(f"  -> ❌ Error processing record: {e}")
            # Use import traceback; traceback.print_exc() for more detail during debugging
            continue

    return {"statusCode": 200, "body": "Filter process complete."}
