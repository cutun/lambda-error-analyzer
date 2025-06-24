# lambda-error-analyzer/run_live.py
import json
import boto3
from botocore.exceptions import ClientError

# Import the main handler function and settings
from lambdas.analyze_logs.app import handler
from lambdas.analyze_logs.models import get_settings

def setup_dynamodb_tables():
    """Checks for and creates all required DynamoDB tables if they don't exist."""
    settings = get_settings()
    dynamodb = boto3.resource('dynamodb', region_name=settings.aws_region)
    
    # --- Table 1: LogAnalysisResults ---
    analysis_table_name = settings.dynamodb_table_name
    try:
        dynamodb.meta.client.describe_table(TableName=analysis_table_name)
        print(f"DynamoDB table '{analysis_table_name}' already exists.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"DynamoDB table '{analysis_table_name}' not found. Creating it now...")
            dynamodb.create_table(
                TableName=analysis_table_name,
                KeySchema=[{'AttributeName': 'analysis_id', 'KeyType': 'HASH'}],
                AttributeDefinitions=[
                    {'AttributeName': 'analysis_id', 'AttributeType': 'S'},
                    {'AttributeName': 'gsi1pk', 'AttributeType': 'S'},
                    {'AttributeName': 'processed_at', 'AttributeType': 'S'}
                ],
                GlobalSecondaryIndexes=[{
                    'IndexName': 'SortByDate',
                    'KeySchema': [
                        {'AttributeName': 'gsi1pk', 'KeyType': 'HASH'},
                        {'AttributeName': 'processed_at', 'KeyType': 'RANGE'}
                    ],
                    'Projection': {'ProjectionType': 'ALL'},
                    'ProvisionedThroughput': {'ReadCapacityUnits': 1, 'WriteCapacityUnits': 1}
                }],
                ProvisionedThroughput={'ReadCapacityUnits': 1, 'WriteCapacityUnits': 1}
            )
            dynamodb.Table(analysis_table_name).wait_until_exists()
            print(f"Table '{analysis_table_name}' created successfully.")
        else: raise e

    # --- Table 2: LogErrorStates ---
    state_table_name = settings.error_state_table_name
    try:
        dynamodb.meta.client.describe_table(TableName=state_table_name)
        print(f"DynamoDB table '{state_table_name}' already exists.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"DynamoDB table '{state_table_name}' not found. Creating it now...")
            dynamodb.create_table(
                TableName=state_table_name,
                KeySchema=[{'AttributeName': 'signature', 'KeyType': 'HASH'}],
                AttributeDefinitions=[{'AttributeName': 'signature', 'AttributeType': 'S'}],
                ProvisionedThroughput={'ReadCapacityUnits': 1, 'WriteCapacityUnits': 1}
            )
            dynamodb.Table(state_table_name).wait_until_exists()
            print(f"Table '{state_table_name}' created successfully.")
        else: raise e

def run_live():
    """Executes the analyze_logs Lambda handler using your live AWS credentials."""
    print("--- Starting LIVE Run of analyze_logs Lambda ---")
    
    try:
        setup_dynamodb_tables()
    except Exception as e:
        print(f"Could not complete setup. Aborting run. Error: {e}")
        return

    try:
        # NOTE: The handler still needs a mock S3 event to run locally.
        # In production, this event comes from the S3 trigger.
        mock_s3_event = {
            "Records": [{
                "s3": {
                    "bucket": {"name": "dummy-bucket"},
                    "object": {"key": "dummy-key"}
                }
            }]
        }
        
        # We also need to mock the S3 file download for local execution
        with patch('lambdas.analyze_logs.app.get_logs_from_s3') as mock_get_logs:
            # Provide the same hardcoded logs your handler used to have
            mock_get_logs.return_value = [
                "2024-06-17T13:31:00Z [ERROR] Authentication failed for user 'jane.doe'. Error: Invalid credentials.",
                "2024-06-17T13:32:00Z [CRITICAL] Core component 'BillingService' has failed.",
                "2024-06-17T13:34:00Z [ERROR] Authentication failed for user 'john.doe'. Error: Invalid credentials.",
                "2024-06-17T13:35:00Z [CRITICAL] Core component 'BillingService' has failed.",
                "2024-06-17T14:00:00Z [WARNING] Disk space is running low on /dev/sda1."
            ]
            
            print("\n--- Invoking Lambda handler (this will call AWS Bedrock and DynamoDB) ---")
            result = handler(mock_s3_event, {})
            print("--- Lambda handler execution finished ---")

        print("\n--- Final JSON Output from Lambda: ---")
        final_output = json.loads(result['body'])
        print(json.dumps(final_output, indent=2))
        
        print(f"\n Success! The analysis result has been saved to the '{get_settings().dynamodb_table_name}' table in DynamoDB.")
    except Exception as e:
        print(f"\n An unexpected error occurred during the run: {e}")


if __name__ == "__main__":
    from unittest.mock import patch # Add import for patch
    run_live()
