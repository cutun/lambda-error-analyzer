import os
import json
import boto3
import uuid
from datetime import datetime, timezone

def handler(event, context):
    """
    This function is triggered by an API Gateway request.
    Its sole purpose is to take the incoming log data from the request body
    and save it as a new object in the designated S3 bucket.
    """
    print("--- Ingest Log Lambda Triggered ---")

    # Get the target S3 bucket name from an environment variable.
    # This is set in the CDK/SAM template.
    
    try:
        delivery_stream = os.environ['DELIVERY_STREAM']
    except KeyError:
        print("❌ FATAL: DELIVERY_STREAM environment variable not set.")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Server configuration error."})
        }

    # The actual log data is in the 'body' of the event from API Gateway
    try:
        log_body = event.get('body')
        if not log_body:        
            print("⚠️ Warning: Request body is empty.")
            return {
                "statusCode": 400,
                "body": json.dumps({"error": "Request body cannot be empty."})
            }

        # Generate a unique filename for the log object using a timestamp and UUID
        # Example: 2025/06/23/18/log-a1b2c3d4.json
        current_time = datetime.now(timezone.utc)
        key_prefix = current_time.strftime('%Y/%m/%d/%H')
        unique_id = uuid.uuid4()
        delivery_key = f"{key_prefix}/log-{unique_id}.txt"

        # Initialize the S3 client
        # s3 = boto3.client('s3')
        firehose = boto3.client('firehose')

        # Upload the log data to Firehose
        firehose.put_record( 
            DeliveryStreamName=delivery_stream,
            Record={"Data": (log_body.rstrip("\n") + "\n").encode()}
        )

        print("✅ Log successfully ingested and saved to S3.")

    except Exception as e:
        print(f"❌ An error occurred during ingestion: {e}")
        # In a real app, you might send this failure to a dead-letter queue
        return {
            "statusCode": 500,
            "body": json.dumps({"error": "Failed to process log."})
        }

    # Return a success response to the API Gateway
    return {
        "statusCode": 202, # 202 Accepted is a good status code for asynchronous processing
        "body": json.dumps({"status": "Log accepted for processing", "s3_key": delivery_key})
    }