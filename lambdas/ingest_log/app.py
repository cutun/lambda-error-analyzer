import json, os, boto3, uuid, datetime as dt
from utils import put_log_object

s3 = boto3.client("s3")
BUCKET = os.environ["LOG_BUCKET"]

def handler(event, context):  # API Gateway v2 HTTP
    body = json.loads(event["body"])
    log_lines = body.get("logs", [])
    timestamp = dt.datetime.utcnow().isoformat()
    key = f"{timestamp}_{uuid.uuid4()}.json"
    put_log_object(s3, BUCKET, key, log_lines)
    return {"statusCode": 200, "body": json.dumps({"key": key})}
