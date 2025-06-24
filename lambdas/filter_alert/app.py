# lambda/filter_alert/app.py
import os
import json
import boto3
import requests
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer
from datetime import datetime, timezone


def unmarshall_dynamodb_item(ddb_item: dict) -> dict:
    """
    Converts a DynamoDB-formatted item into a regular Python dictionary.
    """
    # Create an instance of the deserializer
    class customDeserializer(TypeDeserializer):
        def _deserialize_n(self, value):
            return int(value)
        
    deserializer = customDeserializer()

    # Use a dictionary comprehension to apply the deserializer to every item
    return {k: deserializer.deserialize(v) for k, v in ddb_item.items()}
        

    
    # deserializer = TypeDeserializer()
    # return {k: deserializer.deserialize(v) for k, v in ddb_item.items()}


def filter_alert(alert_data):
    alert_data["clusters"] = list(filter(lambda alert: alert["is_recurring"], alert_data["clusters"]))
    alert_data["total_logs_processed"] = sum(alert["count"] for alert in alert_data["clusters"])
    alert_data["total_clusters_found"] = len(alert_data["clusters"])
    return alert_data


def handler(event, context):
    """
    This handler is triggered by a DynamoDB Stream, filters the result,
    and publishes it to a final SNS topic if it contains recurring errors.
    """
    print("--- FilterAlert Lambda Triggered ---")

    # Initialize the SNS client inside the handler for testability
    sns = boto3.client('sns')
    final_alerts_topic_arn = os.environ['FINAL_ALERTS_TOPIC_ARN']

    records = event.get('Records', [])
    print(f"Received {len(records)} record(s) from the stream.")

    for i, record in enumerate(records):
        print(f"\n--- Processing Record #{i+1} ---\n{json.dumps(record)}")
        try:
            if record.get('eventName') != 'INSERT':
                print(f"  -> Skipping record because eventName is '{record.get('eventName')}', not 'INSERT'.")
                continue

            new_image = record.get('dynamodb', {}).get('NewImage')
            if not new_image:
                print("  -> Skipping record because it has no 'NewImage' data.")
                continue

            # 1. Get the full analysis result from the stream
            analysis_result = unmarshall_dynamodb_item(new_image)
            print("  -> Successfully parsed analysis result from DynamoDB stream.")
            print(f"Parsed Analysis: {json.dumps(analysis_result)}")

            # 2. Run your filter logic
            filtered_result = filter_alert(analysis_result)

            # 3. Check if any clusters remain after filtering
            if filtered_result.get("clusters"):
                print(f"  -> Filter PASSED. Publishing to SNS topic: {final_alerts_topic_arn}")

                # 4. Publish the FILTERED data to the final SNS topic
                sns.publish(
                    TopicArn=final_alerts_topic_arn,
                    Message=json.dumps(filtered_result, default=str),
                    Subject="Action Required: Recurring Error Patterns Detected"
                )
                print("  -> ✅ Filtered alert successfully published to SNS.")
            else:
                print("  -> ℹ️ Filter FAILED. No recurring clusters found. No alert will be sent.")
        
        except Exception as e:
            print(f"  -> ❌ Error processing record: {e}")
            # Continue to the next record in the batch
            continue

    return {"statusCode": 200, "body": "Filter process complete."}
