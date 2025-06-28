# lambda/ingest/app.py
import os
import json
import boto3


# Initialize AWS clients and load configuration in the global scope for reuse.
# This improves performance for "warm" Lambda invocations.
try:
    FIREHOSE_CLIENT = boto3.client('firehose')
    DELIVERY_STREAM_NAME = os.environ['DELIVERY_STREAM']
except KeyError as e:
    # This will cause a Lambda init failure, which is appropriate for missing config.
    print(f"❌ FATAL: Missing required environment variable: {e}")
    FIREHOSE_CLIENT = None
    DELIVERY_STREAM_NAME = None


# Core logic
def ingest_log_data(log_body: str) -> str:
    """
    Takes the raw log data and puts it into the Kinesis Firehose stream.

    Args:
        log_body: The string content of the log(s).

    Returns:
        The RecordId from the Firehose response.
    
    Raises:
        ValueError: If the log_body is empty or None.
        ClientError: If the boto3 call to Firehose fails.
    """
    if not log_body:
        raise ValueError("Request body cannot be empty.")

    # Firehose expects records to be newline-terminated.
    # Ensure the data ends with a newline and is encoded to bytes.
    record_data = (log_body.rstrip("\n") + "\n").encode('utf-8')

    print(f"Putting record of {len(record_data)} bytes into stream: {DELIVERY_STREAM_NAME}")
    response = FIREHOSE_CLIENT.put_record(
        DeliveryStreamName=DELIVERY_STREAM_NAME,
        Record={"Data": record_data}
    )
    
    record_id = response.get("RecordId")
    print(f"✅ Log successfully sent to Firehose. RecordId: {record_id}")
    return record_id

# Lambda handler
def handler(event, context):
    """
    This function is triggered by an API Gateway request. It validates the
    request and passes the body to the ingestion logic.
    """
    print("--- Ingest Log Lambda Triggered ---")
    
    if not all([FIREHOSE_CLIENT, DELIVERY_STREAM_NAME]):
        print("❌ FATAL: Lambda is not configured correctly. Aborting.")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Server configuration error."})
        }

    try:
        log_body = event.get('body')
        
        # The ingest_log_data function will raise a ValueError if the body is empty.
        record_id = ingest_log_data(log_body)

        # 202 Accepted is a good status code for asynchronous processing.
        response_body = {"status": "Log accepted for processing", "recordId": record_id}
        return {
            "statusCode": 202,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(response_body)
        }

    except ValueError as e:
        print(f"⚠️ Bad Request: {e}")
        return {
            "statusCode": 400,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(e)})
        }
    except Exception as e:
        print(f"❌ An unexpected error occurred during ingestion: {e}")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": "Failed to process log."})
        }
