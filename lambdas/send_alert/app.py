# lambda/send_alert/app.py
import os
import json
import boto3
import requests
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer
from datetime import datetime, timezone
from formatter import format_html_body, format_text_body, format_slack_message


def unmarshall_dynamodb_item(ddb_item: dict) -> dict:
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

    AWS_REGION = os.environ.get('AWS_REGION', 'us-east-2')
    RECIPIENT_EMAIL = [email.strip() for email in os.environ.get('RECIPIENT_EMAIL').split(",")]
    SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
    SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

    message_string = event['Records'][0]['Sns']['Message']
    alert_data = json.loads(message_string)
    
    # Re-initialize client inside handler to be safe in different environments
    ses_client = boto3.client('ses', region_name=AWS_REGION)
    ssm_client = boto3.client('ssm', region_name=AWS_REGION)

    # For reading subscription list in future
    dynamodb_resource = boto3.resource('dynamodb')

    try:
        # 1. Parse the incoming event from SNS
        print("Parsing message from SNS event...")
        message_string = event['Records'][0]['Sns']['Message']
        analysis_result = json.loads(message_string)
        print(f"Successfully parsed analysis result for ID: {analysis_result.get('analysis_id')}")
        
        # --- Slack Notification Logic ---
        if SLACK_WEBHOOK_URL:
            try:
                print("Formatting and sending Slack message...")
                slack_payload = format_slack_message(analysis_result)
                print("slack payload to send:", slack_payload)
                response = requests.post(SLACK_WEBHOOK_URL, json=slack_payload)
                response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
                print("✅ Message sent to Slack successfully.")
            except Exception as e:
                # Log the error but don't stop the function
                print(f"⚠️ Could not send Slack notification: {e}")
        else:
            print("ℹ️ SLACK_WEBHOOK_URL not set. Skipping Slack notification.")

        # --- Email Notification Logic ---
        if SENDER_EMAIL and RECIPIENT_EMAIL:
            try:
                print(f"Formatting and sending email to: {RECIPIENT_EMAIL}")
                send_formatted_email(ses_client, analysis_result, SENDER_EMAIL, RECIPIENT_EMAIL)
                print("✅ Email sent successfully.")
            except Exception as e:
                print(f"⚠️ Could not send email notification: {e}")
        else:
            print("ℹ️ Email variables not set. Skipping email notification.")

    except (KeyError, IndexError, TypeError) as e:
        print(f"❌ CRITICAL ERROR: Could not parse the incoming SNS event. Check the event structure. Error: {e}")
        # Re-raise the error to mark this Lambda execution as failed
        raise e

    return {"statusCode": 200, "body": "Alert processed."}
