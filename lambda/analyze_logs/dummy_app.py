# handlers/log_analysis/dummy_app.py
import os
import json
import boto3

# Get the ARN of the SNS topic from an environment variable
SNS_TOPIC_ARN = os.environ['ALERTS_SNS_TOPIC_ARN']
sns = boto3.client('sns')

def handler(event, context):
    print("Log Analysis Handler Triggered")
    
    # In the real app, this would analyze the event and decide if an alert is needed.
    # For now, create and publish an alert for every log received.
    
    alert_payload = {
        "level": "CRITICAL",
        "error_message": "This is a test alert from the Log Analysis Lambda",
        "details": {"source_ip": event.get("requestContext", {}).get("http", {}).get("sourceIp", "Unknown")}
    }

    print("Publishing alert to SNS...")
    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Message=json.dumps(alert_payload),
        Subject="New Critical Alert Detected"
    )
    
    # This is the response that goes back to the API Gateway
    return {
        "statusCode": 200,
        "body": json.dumps({"status": "log processed"})
    }