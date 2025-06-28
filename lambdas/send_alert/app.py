# lambda/send_alert/app.py
import os
import json
import boto3
import requests
from botocore.exceptions import ClientError
import time

# Importing lambda-specific modules
from formatter import format_html_body, format_text_body, format_slack_message

# Configuration
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL')
SLACK_WEBHOOK_URL = os.environ.get('SLACK_WEBHOOK_URL')

# Safely parse the recipient email list
RECIPIENT_EMAILS_STR = os.environ.get('RECIPIENT_EMAIL', '').strip()
RECIPIENT_EMAIL = [email.strip() for email in RECIPIENT_EMAILS_STR.split(",")] if RECIPIENT_EMAILS_STR else []

# Initialize AWS clients
ses_client = boto3.client('ses', region_name=AWS_REGION)


def parse_incoming_event(event: dict) -> dict | None:
    """Parses the SNS message from the incoming event."""
    try:
        print("Parsing message from SNS event...")
        message_string = event['Records'][0]['Sns']['Message']
        analysis_result = json.loads(message_string)
        print(f"Successfully parsed analysis result for ID: {analysis_result.get('analysis_id')}")
        return analysis_result
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as e:
        print(f"❌ CRITICAL ERROR: Could not parse the incoming SNS event. Check the event structure. Error: {e}")
        return None

def send_slack_notification(webhook_url: str, analysis_result: dict) -> None:
    """Formats and sends a Slack notification in batches."""
    if not webhook_url:
        print("ℹ️ SLACK_WEBHOOK_URL not set. Skipping Slack notification.")
        return
        
    total_clusters = analysis_result.get("total_clusters_found", 0)
    if not total_clusters:
        return

    batch_size = 15 # The most Slack can display without rejecting
    num_batches = (total_clusters + batch_size - 1) // batch_size
    clusters_to_process = analysis_result.get("clusters", [])

    for i in range(num_batches):
        batch_num = i + 1
        start_index = i * batch_size
        end_index = start_index + batch_size
        batch_clusters = clusters_to_process[start_index:end_index]
        batch_analysis_result = {**analysis_result, "clusters": batch_clusters}
        
        try:
            print(f"Formatting and sending Slack message... ({batch_num}/{num_batches})")
            slack_payload = format_slack_message(batch_analysis_result, batch_num, num_batches)
            response = requests.post(webhook_url, json=slack_payload, timeout=10)
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Could not send Slack notification due to a network error: {e}")
            return
        time.sleep(1) # Avoid rate-limiting
    print(f"✅ All {num_batches} message(s) sent to Slack successfully.")

def send_email_notification(ses, sender: str, recipients: list[str], analysis_result: dict) -> None:
    """Formats and sends an email notification in batches."""
    if not (sender and recipients):
        print("ℹ️ Email variables not set. Skipping email notification.")
        return
        
    total_clusters = analysis_result.get("total_clusters_found", 0)
    if not total_clusters:
        return

    batch_size = 100 # A reasonable limit for email body size
    num_batches = (total_clusters + batch_size - 1) // batch_size
    clusters_to_process = analysis_result.get("clusters", [])

    for i in range(num_batches):
        batch_num = i + 1
        start_index = i * batch_size
        end_index = start_index + batch_size
        batch_clusters = clusters_to_process[start_index:end_index]
        batch_analysis_result = {**analysis_result, "clusters": batch_clusters}

        print(f"Formatting and sending email from '{sender}' to: {', '.join(recipients)} ({batch_num}/{num_batches})")
        subject = "[Alert] Log Analysis Digest"
        if num_batches > 1:
            subject += f" ({batch_num}/{num_batches})"
        
        # Pass the complete batch object to the formatters
        html_body = format_html_body(batch_analysis_result, batch_num, num_batches)
        text_body = format_text_body(batch_analysis_result)

        try:
            ses.send_email(
                Destination={'ToAddresses': [sender], 'BccAddresses': recipients},
                Message={
                    'Body': {'Html': {'Charset': "UTF-8", 'Data': html_body}, 'Text': {'Charset': "UTF-8", 'Data': text_body}},
                    'Subject': {'Charset': "UTF-8", 'Data': subject},
                },
                Source=sender,
            )
        except ClientError as e:
            print(f"⚠️ Could not send email notification due to AWS SES error: {e.response['Error']['Message']}")
            return
        time.sleep(1) # Avoid rate-limiting
    print(f"✅ All {num_batches} email(s) sent successfully. ")


def handler(event, context):
    """
    Main Lambda handler to process log analysis results and send alerts.
    """
    analysis_result = parse_incoming_event(event)
    if not analysis_result:
        return {"statusCode": 400, "body": "Failed to parse incoming event."}

    # No need for deepcopy here as the notification functions are now pure.
    send_slack_notification(SLACK_WEBHOOK_URL, analysis_result)
    send_email_notification(ses_client, SENDER_EMAIL, RECIPIENT_EMAIL, analysis_result)

    return {"statusCode": 200, "body": "Alert processed."}
