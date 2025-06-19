# send_test_email.py
import boto3
from botocore.exceptions import ClientError
from cli.push_log import create_log_payload

# --- CONFIGURATION ---
# Use the same email address you verified in the AWS SES Console for both.
SENDER_EMAIL = "eric20050708@gmail.com"
RECIPIENT_EMAIL = "eric20050708@gmail.com"

# The AWS Region where you verified your email identity (e.g., "us-east-2").
AWS_REGION = "us-east-2"
# ---------------------------------------------


def send_test_email():
    """
    Uses boto3 to create an SES client and send a simple test email.
    """
    # Create a new client with the specified region
    ses_client = boto3.client('ses', region_name=AWS_REGION)

    # Email content
    subject = "Amazon SES Test from Boto3 Script"
    body_text = ("\n"
        "Lambda-Error-Analyzer Test EMail")

    print(f"Attempting to send an email from {SENDER_EMAIL} to {RECIPIENT_EMAIL}...")

    try:
        # Provide the contents of the email.
        response = ses_client.send_email(
            Destination={
                'ToAddresses': [
                    RECIPIENT_EMAIL,
                ],
            },
            Message={
                'Body': {
                    'Text': {
                        'Charset': "UTF-8",
                        'Data': body_text,
                    },
                },
                'Subject': {
                    'Charset': "UTF-8",
                    'Data': subject,
                },
            },
            Source=SENDER_EMAIL,
        )

    # Display an error if something goes wrong (e.g., email not verified).
    except ClientError as e:
        print("❌ An error occurred:")
        print(e.response['Error']['Message'])
    else:
        print("✅ Email sent! Message ID:")
        print(response['MessageId'])


# This block allows the script to be run directly from the terminal
if __name__ == "__main__":
    send_test_email()