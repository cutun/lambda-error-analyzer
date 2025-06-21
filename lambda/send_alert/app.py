# lambda/send_alert/app.py
import os
import json
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer
from datetime import datetime, timezone
from formatter import format_html_body, format_text_body


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
    
    # Re-initialize client inside handler to be safe in different environments
    ses_client = boto3.client('ses', region_name=AWS_REGION)
    dynamodb_resource = boto3.resource('dynamodb')

    for record in event.get('Records', []):
        # Only care about new analysis results being inserted
        if record.get('eventName') != 'INSERT':
            continue
        new_image = record['dynamodb'].get('NewImage')
        if not new_image:
            continue
        alert_data = unmarshall_dynamodb_item(new_image)
        send_formatted_email(ses_client, alert_data, SENDER_EMAIL, RECIPIENT_EMAIL)

    return {"statusCode": 200, "body": "Alert processed."}


# --- Local Test Runner (This block will now send a REAL email) ---

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    print("--- Running Local Test to Send a REAL Email ---")

    # IMPORTANT: Fill this with only verified email address
    recipient = "eric20050708@gmail.com"
    sender = "eric20050708@gmail.com"
    region = "us-east-2" # change this to the region you verified AWS SSE identity
    
    # 1. Create sample data 
    fake_event = {
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

