# lambdas/get_history/database_querier.py
import os
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

# Initialize resources once for Lambda container reuse
HISTORY_TABLE_NAME = os.environ.get("HISTORY_TABLE_NAME", "LogHistoryTable")
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(HISTORY_TABLE_NAME)

def get_occurrence_count(signature: str, start_time_iso: str) -> int:
    """
    Queries DynamoDB to get the count of occurrences for a signature after a given time.

    Args:
        signature: The error signature partition key.
        start_time_iso: The ISO 8601 timestamp to query after.

    Returns:
        The number of items found.
    """
    print(f"Querying for signature '{signature}' since {start_time_iso}...")

    try:
        # Query the table for items with the given signature (partition key)
        # and a timestamp (sort key) greater than our start time.
        response = table.query(
            KeyConditionExpression=
                Key('signature').eq(signature) & Key('timestamp').gt(start_time_iso),
            # We only need the count, so we can make the query more efficient.
            Select='COUNT'
        )
        
        # The number of items found is the count
        error_count = response.get('Count', 0)
        return error_count
        
    except ClientError as e:
        print(f"Error querying DynamoDB: {e}")
        # Re-raise the exception to be handled by the main handler
        raise
