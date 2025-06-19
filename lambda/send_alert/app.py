# handlers/send_alert/app.py
import os
import json
import boto3
from botocore.exceptions import ClientError

# Get configuration from environment variables
RECIPIENT_EMAIL = os.environ['RECIPIENT_EMAIL']
SENDER_EMAIL = os.environ['SENDER_EMAIL']
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

ses_client = boto3.client('ses', region_name=AWS_REGION)

def handler(event, context):
    # Extract the alert data from the SNS message
    message_str = event['Records'][0]['Sns']['Message']
    alert_data = json.loads(message_str)
    
    # Format the email content
    subject = f"[ALERT] {alert_data.get('level', 'INFO')}: {alert_data.get('error_message', 'Alert')}"
    body_text = "An alert has been triggered by the lambda-error-analyzer.\n\n--- Details ---\n"
    body_text += json.dumps(alert_data, indent=2)

    # Send the email using SES
    try:
        ses_client.send_email(
            Destination={'ToAddresses': [RECIPIENT_EMAIL]},
            Message={
                'Body': {'Text': {'Charset': "UTF-8", 'Data': body_text}},
                'Subject': {'Charset': "UTF-8", 'Data': subject},
            },
            Source=SENDER_EMAIL
        )
        print("✅ Email sent successfully via SES.")
    except ClientError as e:
        print(f"❌ Error sending email: {e}")
        raise e

    return {"statusCode": 200, "body": "Alert processed."}