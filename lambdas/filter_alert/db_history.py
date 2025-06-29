# lambda/filter_alert/db_history.py
import os
from datetime import datetime, timezone, timedelta
import boto3
from botocore.exceptions import ClientError
from boto3.dynamodb.types import TypeDeserializer
from collections import defaultdict

# Initialize resources once for Lambda container reuse.
try:
    DYNAMODB_RESOURCE = boto3.resource('dynamodb')
    HISTORY_TABLE_NAME = os.environ['HISTORY_TABLE_NAME']
    HISTORY_TABLE = DYNAMODB_RESOURCE.Table(HISTORY_TABLE_NAME)
except KeyError as e:
    print(f"FATAL: Missing required environment variable: {e}")
    HISTORY_TABLE = None

# Custom Deserializer to handle DynamoDB Stream data format.
class DynamoDBDeserializer(TypeDeserializer):
    def _deserialize_n(self, value):
        return int(value) if value.isdigit() else float(value)

DDB_DESERIALIZER = DynamoDBDeserializer()

def unmarshall_dynamodb_item(ddb_item: dict) -> dict:
    """Converts a DynamoDB-formatted item from a stream into a regular Python dictionary."""
    return {k: DDB_DESERIALIZER.deserialize(v) for k, v in ddb_item.items()}


# BATCH DATA ACCESS FUNCTIONS

def get_batch_historical_timestamps(signatures: list[str]) -> dict[str, list[str]]:
    """
    Fetches a recent, limited history of timestamps for multiple signatures.
    This function iterates and performs an efficient QUERY for each signature,
    which is the correct way to fetch a subset of items from a partition.

    Args:
        signatures: A list of unique error signature strings.

    Returns:
        A dictionary mapping each signature to its list of recent historical timestamps.
    """
    if not HISTORY_TABLE or not signatures:
        return {}
    
    historical_data = defaultdict(list)
    
    print(f" -> Fetching recent history for {len(signatures)} unique signatures...")

    for sig in signatures:
        try:
            # A QUERY is the correct and efficient way to get multiple items
            # from a single partition (signature). We limit the results to
            # prevent pulling thousands of records.
            response = HISTORY_TABLE.query(
                KeyConditionExpression='signature = :sig',
                ExpressionAttributeValues={
                    ':sig': sig
                },
                # Scan backwards to get the newest items first
                ScanIndexForward=False,
                # Limit the number of records to a reasonable history size
                Limit=10000,
                ProjectionExpression='#ts', # Only fetch the timestamp
                ExpressionAttributeNames={'#ts': 'timestamp'}
            )
            
            items = response.get('Items', [])
            # The timestamps will be newest-to-oldest, so we reverse them
            # to get the correct chronological order for our models.
            historical_data[sig] = [item['timestamp'] for item in reversed(items)]
            
        except ClientError as e:
            print(f" -> ❌ DynamoDB query failed for signature '{sig}': {e.response['Error']['Message']}")
            # Continue to the next signature even if one fails
            continue
            
    print(f" -> Found history for {len(historical_data)} signatures.")
    return historical_data

def batch_update_history(history_items_to_write: list[dict]):
    """
    Writes a list of timestamp items to the history table using a single batch writer context.

    Args:
        history_items_to_write: A list of dicts, each being {'signature': str, 'timestamp': str}.
    """
    if not HISTORY_TABLE or not history_items_to_write:
        return
        
    print(f" -> Writing {len(history_items_to_write)} total events to history...")
    try:
        with HISTORY_TABLE.batch_writer() as batch:
            for item in history_items_to_write:
                # Set a Time-To-Live (TTL) of 48 hours for automatic cleanup
                ttl_timestamp = int((datetime.now(timezone.utc) + timedelta(hours=48)).timestamp())
                batch.put_item(
                    Item={
                        'signature': item['signature'],
                        'timestamp': item['timestamp'],
                        'ttl': ttl_timestamp
                    }
                )
        print(f" -> ✅ Successfully updated history with {len(history_items_to_write)} events.")
    except ClientError as e:
        print(f" -> ❌ DynamoDB batch_writer failed: {e.response['Error']['Message']}")

