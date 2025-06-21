# lambda-error-analyzer/run_live.py
import json
import boto3
from botocore.exceptions import ClientError

# Import the main handler function and settings
from lambdas.analyze_logs.app import handler
from lambdas.analyze_logs.models import get_settings

def setup_dynamodb_table():
    """Checks for the DynamoDB table and creates it with a Global Secondary Index if it doesn't exist."""
    settings = get_settings()
    dynamodb = boto3.resource('dynamodb', region_name=settings.aws_region)
    table_name = settings.dynamodb_table_name
    
    try:
        dynamodb.meta.client.describe_table(TableName=table_name)
        print(f"DynamoDB table '{table_name}' already exists.")
    except ClientError as e:
        if e.response['Error']['Code'] == 'ResourceNotFoundException':
            print(f"DynamoDB table '{table_name}' not found. Creating it now with a GSI for sorting...")
            try:
                dynamodb.create_table(
                    TableName=table_name,
                    # --- Main Primary Key ---
                    KeySchema=[
                        {'AttributeName': 'analysis_id', 'KeyType': 'HASH'}  # Partition key
                    ],
                    AttributeDefinitions=[
                        {'AttributeName': 'analysis_id', 'AttributeType': 'S'},
                        # --- NEW: Define attributes for the GSI ---
                        {'AttributeName': 'gsi1pk', 'AttributeType': 'S'},
                        {'AttributeName': 'processed_at', 'AttributeType': 'S'}
                    ],
                    # --- NEW: Define the Global Secondary Index for sorting by date ---
                    GlobalSecondaryIndexes=[
                        {
                            'IndexName': 'SortByDate',
                            'KeySchema': [
                                {'AttributeName': 'gsi1pk', 'KeyType': 'HASH'}, # GSI Partition Key
                                {'AttributeName': 'processed_at', 'KeyType': 'RANGE'} # GSI Sort Key
                            ],
                            'Projection': {
                                'ProjectionType': 'ALL' # Include all attributes in the index
                            },
                            'ProvisionedThroughput': {'ReadCapacityUnits': 1, 'WriteCapacityUnits': 1}
                        }
                    ],
                    ProvisionedThroughput={'ReadCapacityUnits': 1, 'WriteCapacityUnits': 1}
                )
                print(f"Waiting for table '{table_name}' to become active...")
                table = dynamodb.Table(table_name)
                table.wait_until_exists()
                print(f"Table '{table_name}' created successfully.")
            except ClientError as create_error:
                print(f"Error creating DynamoDB table: {create_error}")
                raise
        else:
            print(f"An unexpected error occurred with DynamoDB: {e}")
            raise

def run_live():
    """Executes the analyze_logs Lambda handler using your live AWS credentials."""
    print("--- Starting LIVE Run of analyze_logs Lambda ---")
    
    try:
        setup_dynamodb_table()
    except Exception as e:
        print(f"Could not complete setup. Aborting run. Error: {e}")
        return

    try:
        print("\n--- Invoking Lambda handler (this will call AWS Bedrock and DynamoDB) ---")
        result = handler({}, {})
        print("--- Lambda handler execution finished ---")

        print("\n--- Final JSON Output from Lambda: ---")
        final_output = json.loads(result['body'])
        print(json.dumps(final_output, indent=2))
        
        print(f"\n Success! The analysis result has been saved to the '{get_settings().dynamodb_table_name}' table in DynamoDB.")
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code")
        print(f"\n An AWS error occurred: {error_code}")
        print(f"   Message: {e}")
        if error_code == 'AccessDeniedException':
            print(" Suggestion: Check IAM permissions for 'bedrock:InvokeModel' and DynamoDB actions.")
        elif error_code == 'ValidationException':
             print("   Suggestion: The Bedrock model ID or API request format may be incorrect.")
    except Exception as e:
        print(f"\n An unexpected error occurred during the run: {e}")

if __name__ == "__main__":
    run_live()
