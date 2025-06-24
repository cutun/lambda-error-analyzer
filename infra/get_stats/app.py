# lambda_error_analyzer/lambdas/get_stats/app.py
import json
import boto3
from boto3.dynamodb.conditions import Key
import os

# Initialize clients outside the handler for reuse
DYNAMODB_TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "LogAnalysisResults")
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

def handler(event: dict, context: object) -> dict:
    """
    API Gateway handler to fetch the most recent log analysis result.
    This function acts as the backend for the /stats endpoint for the UI.
    """
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # Query the Global Secondary Index (GSI) to get the latest item.
        # 'gsi1pk' is the static partition key for all analysis results.
        # We scan forward and limit to 1 to get the single most recent item.
        response = table.query(
            IndexName='SortByDate',
            KeyConditionExpression=Key('gsi1pk').eq('ANALYSIS_RESULT'),
            ScanIndexForward=False,  # Sort by date descending (newest first)
            Limit=1
        )
        
        if response.get('Items'):
            # The most recent analysis result is the first item
            latest_result = response['Items'][0]
            
            print("Successfully fetched the latest analysis result.")
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*' # Allow frontend access
                },
                'body': json.dumps(latest_result, default=str) # Use default=str to handle Decimals
            }
        else:
            # This case handles when the table is empty
            print("No analysis results found in the table.")
            return {
                'statusCode': 404,
                 'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
                'body': json.dumps({'message': 'No analysis results found.'})
            }

    except Exception as e:
        print(f"Error fetching data from DynamoDB: {e}")
        return {
            'statusCode': 500,
             'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                },
            'body': json.dumps({'message': 'Internal server error.'})
        }
