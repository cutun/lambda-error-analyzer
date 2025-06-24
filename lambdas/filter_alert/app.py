# lambda/filter_alert/app.py
import os
import json
import boto3
import requests
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer
from datetime import datetime, timezone


def unmarshall_dynamodb_item(ddb_item):
    """Converts a DynamoDB-formatted item into a regular Python dictionary."""
    deserializer = TypeDeserializer()
    return {k: deserializer.deserialize(v) for k, v in ddb_item.items()}


def filter_alert(alert_data):
    alert_data["clusters"] = list(filter(lambda alert: alert["is_recurring"], alert_data["clusters"]))
    alert_data["total_logs_processed"] = sum(alert["count"] for alert in alert_data["clusters"])
    alert_data["total_clusters_found"] = len(alert_data["clusters"])
    return alert_data


def handler(event, context):
    """
    This is the main function that runs in AWS Lambda.
    """
    AWS_REGION = os.environ.get('AWS_REGION', 'us-east-2')
    SNS_TOPIC_ARN = os.environ['FINAL_ALERTS_TOPIC_ARN']
    sns_client = boto3.client('sns', region_name=AWS_REGION)
    dynamodb_resource = boto3.resource('dynamodb', region_name=AWS_REGION)

    payload = ""
    for record in event.get('Records', []):
        # Only care about new analysis results being inserted
        if record.get('eventName') != 'INSERT':
            continue
        new_image = record['dynamodb'].get('NewImage')
        if not new_image:
            continue
        alert_data = unmarshall_dynamodb_item(new_image)
        filtered_alert_data = filter_alert(alert_data)
        if not filtered_alert_data.get("clusters"):
            continue
        sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Message=json.dumps(filtered_alert_data),
            Subject="Action Required: Recurring Error Patterns Detected"
        )
    return {"statusCode": 200, "body": "Alert filtered."}