# handlers/send_alert/app.py
import os
import json
import boto3
from botocore.exceptions import ClientError
from datetime import datetime, timezone

# --- Production Code (This part is for when it runs in AWS Lambda) ---

ses_client = boto3.client('ses')

def format_html_body(alert_data):
    """Takes the alert data and builds a nice-looking HTML string."""
    styles = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { border: 1px solid #e1e4e8; padding: 20px; max-width: 600px; margin: 20px auto; border-radius: 6px; }
        .header { background-color: #d73a49; color: white; padding: 12px; text-align: center; border-radius: 6px 6px 0 0; font-size: 24px; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #e1e4e8; }
        th { background-color: #f6f8fa; font-weight: 600; }
        code { background-color: #f6f8fa; padding: 2px 4px; border-radius: 3px; font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace; }
    </style>
    """
    rows = ""
    for key, value in alert_data.items():
        rows += f"<tr><th>{key}</th><td><code>{json.dumps(value)}</code></td></tr>"

    html = f"""
    <html><head>{styles}</head><body>
        <div class="container">
            <div class="header">🚨 Alert Detected!</div>
            <p>An automated alert has been triggered by the lambda-error-analyzer system.</p>
            <table>{rows}</table>
        </div>
    </body></html>
    """
    return html

def format_text_body(alert_data):
    """Creates a plain text version of the alert."""
    text = "An alert has been triggered by the lambda-error-analyzer.\n\n--- Details ---\n"
    for key, value in alert_data.items():
        text += f"{key}: {json.dumps(value)}\n"
    return text

def handler(event, context):
    """
    This is the main function that runs in AWS Lambda.
    """
    AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')
    RECIPIENT_EMAIL = os.environ['RECIPIENT_EMAIL']
    SENDER_EMAIL = os.environ['SENDER_EMAIL']
    
    # Re-initialize client inside handler to be safe in different environments
    ses = boto3.client('ses', region_name=AWS_REGION)

    print("--- HTML Email Alert Lambda Triggered ---")
    try:
        alert_data = json.loads(event['Records'][0]['Sns']['Message'])
        subject = f"[{alert_data.get('level', 'ALERT')}] {alert_data.get('error_message', 'New Alert')}"
        html_body = format_html_body(alert_data)
        text_body = format_text_body(alert_data)

        print(f"Sending formatted email to {RECIPIENT_EMAIL}...")
        ses.send_email(
            Destination={'ToAddresses': [RECIPIENT_EMAIL]},
            Message={
                'Body': {'Html': {'Charset': "UTF-8", 'Data': html_body}, 'Text': {'Charset': "UTF-8", 'Data': text_body}},
                'Subject': {'Charset': "UTF-8", 'Data': subject},
            },
            Source=SENDER_EMAIL,
        )
        print(f"✅ Email sent to {RECIPIENT_EMAIL} via SES.")
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        raise e
    return {"statusCode": 200, "body": "Alert processed."}


# --- Local Test Runner (This block will now send a REAL email) ---

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    print("--- Running Local Test to Send a REAL Email ---")

    # IMPORTANT: Fill this in with your verified email address
    my_verified_email = "eric20050708@gmail.com"
    region = "us-east-2" # change this to the region you verified AWS SSE identity
    
    # 1. Create sample data to simulate the SNS trigger
    fake_event = {
        "Records": [{"Sns": {"Message": json.dumps({
            "level": "TEST",
            "error_message": "If you see this message, email test is successful",
            "details": "Send me Skirk funds!"
        })}}]
    }

    # 2. Set the environment variables that the handler needs
    os.environ['RECIPIENT_EMAIL'] = my_verified_email
    os.environ['SENDER_EMAIL'] = my_verified_email
    os.environ['AWS_REGION'] = region

    # 3. Call the handler directly
    try:
        handler(fake_event, None)
    finally:
        # 4. Clean up the environment variables
        del os.environ['RECIPIENT_EMAIL']
        del os.environ['SENDER_EMAIL']
        del os.environ['AWS_REGION']