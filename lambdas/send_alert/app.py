# lambda/send_alert/app.py
import os
import json
import boto3
import requests
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer
from datetime import datetime, timezone
from formatter import format_html_body, format_text_body, format_slack_message


def unmarshall_dynamodb_item(ddb_item):
    """Converts a DynamoDB-formatted item into a regular Python dictionary."""
    deserializer = TypeDeserializer()
    return {k: deserializer.deserialize(v) for k, v in ddb_item.items()}


def send_formatted_email(ses, alert_data, sender_email, recipients):
    subject = "[Alert]-New Log Analysis"
    html_body = format_html_body(alert_data)
    text_body = format_text_body(alert_data)

    ses.send_email(
        Destination={
            'ToAddresses': [sender_email],
            'BccAddresses': recipients},
        Message={
            'Body': {'Html': {'Charset': "UTF-8", 'Data': html_body}, 'Text': {'Charset': "UTF-8", 'Data': text_body}},
            'Subject': {'Charset': "UTF-8", 'Data': subject},
        },
        Source=sender_email,
    )


def handler(event, context):
    """
    This is the main function that runs in AWS Lambda.
    """
    AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
    RECIPIENT_EMAIL = [email.strip() for email in os.environ['RECIPIENT_EMAIL'].split(",")]
    SENDER_EMAIL = os.environ['SENDER_EMAIL']
    SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

    event = json.loads(event)
    
    # Re-initialize client inside handler to be safe in different environments
    ses_client = boto3.client('ses', region_name=AWS_REGION)
    ssm_client = boto3.client('ssm', region_name=AWS_REGION)
    dynamodb_resource = boto3.resource('dynamodb')

    for record in event.get('Records', []):
        # Only care about new analysis results being inserted
        if record.get('eventName') != 'INSERT':
            continue
        new_image = record['dynamodb'].get('NewImage')
        if not new_image:
            continue
        alert_data = unmarshall_dynamodb_item(new_image)
        if SLACK_WEBHOOK_URL:
            # param = ssm_client.get_parameter(Name=SLACK_WEBHOOK_URL, WithDecryption=True)
            # webhook_url = param['Parameter']['Value']
            slack_payload = format_slack_message(alert_data)
            response = requests.post(SLACK_WEBHOOK_URL, json=slack_payload)
            response.raise_for_status()
        
        send_formatted_email(ses_client, alert_data, SENDER_EMAIL, RECIPIENT_EMAIL) 

    return {"statusCode": 200, "body": "Alert processed."}


# --- Local Test Runner (This block will now send a REAL email) ---
import json
from boto3.dynamodb.types import TypeSerializer

def create_dynamodb_stream_event(new_item_dict: dict) -> dict:
    """
    Takes a standard Python dictionary, marshalls it into DynamoDB format,
    and wraps it in a realistic DynamoDB Stream 'INSERT' event structure.
    """
    serializer = TypeSerializer()

    # 1. Marshall the Python dict into DynamoDB's format
    dynamodb_json = {k: serializer.serialize(v) for k, v in new_item_dict.items()}

    # 2. Wrap it in the full event envelope
    fake_event = {
        "Records": [
            {
                "eventID": "a1b2c3d4e5f67890",
                "eventName": "INSERT", # Critical for your handler's logic
                "eventVersion": "1.1",
                "eventSource": "aws:dynamodb",
                "awsRegion": "us-east-1",
                "dynamodb": {
                    "ApproximateCreationDateTime": 1672531200,
                    "Keys": {
                        # In a real event, the primary key would be here
                        "analysis_id": dynamodb_json.get("analysis_id")
                    },
                    "NewImage": dynamodb_json, # <-- Your marshalled data goes here
                    "SequenceNumber": "111122223333",
                    "SizeBytes": 1024,
                    "StreamViewType": "NEW_IMAGE"
                },
                "eventSourceARN": "arn:aws:dynamodb:us-east-1:..."
            }
        ]
    }
    return fake_event


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    print("--- Running Local Test to Send a REAL Email ---")

    # IMPORTANT: Fill this with only verified email address
    recipient = "eric20050708@gmail.com"
    sender = "eric20050708@gmail.com"
    region = "us-east-2" # change this to the region you verified AWS SSE identity

    # 1. Create sample data 
    fake_json = {
        "analysis_id": "cbadcde7-86e9-4e76-8f4c-f8b1282d874f",
        "summary": "Error communicating with Bedrock API: An error occurred (ValidationException) when calling the InvokeModel operation: Malformed input request: #: extraneous key [anthropic_version] is not permitted, please reformat your input and try again.",
        "total_logs_processed": 7,
        "total_clusters_found": 3,
        "clusters": [
        {
        "signature": "Error: Invalid credentials.",
        "count": 3,
        "log_samples": [
            "2024-06-17T13:32:00Z [ERROR] Authentication failed for user 'jane.doe'. Error: Invalid credentials.",
            "2024-06-17T13:35:00Z [ERROR] Authentication failed for user 'john.doe'. Error: Invalid credentials."
        ],
        "representative_log": "2024-06-17T13:35:00Z [ERROR] Authentication failed for user 'jane.doe'. Error: Invalid credentials."
        },
        {
        "signature": "CRITICAL: Core component 'BillingService' has failed.",
        "count": 2,
        "log_samples": [
            "2024-06-17T13:32:00Z [CRITICAL] Core component 'BillingService' has failed.",
            "2024-06-17T13:35:00Z [CRITICAL] Core component 'BillingService' has failed."
        ],
        "representative_log": "2024-06-17T13:32:00Z [CRITICAL] Core component 'BillingService' has failed."
        },
        {
        "signature": "WARNING: Disk space is running low on /dev/hda1.",
        "count": 2,
        "log_samples": [
            "2024-06-17T14:00:00Z [WARNING] Disk space is running low on /dev/hda1."
        ],
        "representative_log": "2024-06-17T14:00:00Z [WARNING] Disk space is running low on /dev/hda1."
        }
        ],
        "processed_at": "2025-06-20T23:59:45.585957Z",
        "gsi1pk": "ANALYSIS_RESULT"
    }

    fake_event = create_dynamodb_stream_event(fake_json)

    # 2. Set the environment variables that the handler needs
    os.environ['RECIPIENT_EMAIL'] = recipient
    os.environ['SENDER_EMAIL'] = sender
    os.environ['AWS_REGION'] = region

    # 3. Call the handler directly
    try:
        pass
        handler(json.dumps(fake_event), None)
    finally:
        # 4. Clean up the environment variables
        del os.environ['RECIPIENT_EMAIL']
        del os.environ['SENDER_EMAIL']
        del os.environ['AWS_REGION']

