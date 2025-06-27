# lambdas/get_history/app.py
import os
import json
import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timedelta, timezone

HISTORY_TABLE_NAME = os.environ.get("HISTORY_TABLE_NAME", "LogHistoryTable")
ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN")

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(HISTORY_TABLE_NAME)

def handler(event: dict, context: object) -> dict:
    """
    API Gateway handler to fetch the history for a specific error signature.
    This can be used by a frontend to display trends and counts.
    
    Expected query string parameters:
    - signature: The error signature to look up (required).
    - hours: The time window in hours to look back (optional, default is 24).
    """
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # in here we would get the parameters from API gateway
        query_params = event.get('queryStringParameters') or {}
        signature = query_params.get('signature')
        
        if not signature:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': ALLOWED_ORIGIN},
                'body': json.dumps({'message': 'Missing required query parameter: signature'})
            }
            
        try:
            hours_lookback = int(query_params.get('hours', 24))
        except ValueError:
            return {
                'statusCode': 400,
                'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': ALLOWED_ORIGIN},
                'body': json.dumps({'message': 'Invalid query parameter: hours must be an integer.'})
            }

        # Query DynamoDB for the requested historyk
        
        # Calculate the start time for the query
        start_time = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)
        start_time_iso = start_time.isoformat()

        print(f"Querying for signature '{signature}' since {start_time_iso}...")

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
        
        print(f"Found {error_count} occurrences in the last {hours_lookback} hours.")
        
        # Return the result
        result_body = {
            'signature': signature,
            'lookback_hours': hours_lookback,
            'occurrence_count': error_count
        }

        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                # Use the specific origin
                'Access-Control-Allow-Origin': ALLOWED_ORIGIN
            },
            'body': json.dumps(result_body)
        }

    except Exception as e:
        print(f"Error fetching data from DynamoDB: {e}")
        return {
            'statusCode': 500,
            'headers': {'Content-Type': 'application/json', 'Access-Control-Allow-Origin': '*'},
            'body': json.dumps({'message': 'Internal server error.'})
        }