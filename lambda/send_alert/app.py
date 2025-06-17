import os, json, boto3

sns = boto3.client("sns")
TOPIC_ARN = os.environ["ALERT_TOPIC"]

def handler(event, context):
    message = json.loads(event["Records"][0]["Sns"]["Message"])
    sns.publish(
        TopicArn=TOPIC_ARN,
        Message=json.dumps(message, indent=2),
        Subject=f"[lambda-error-analyzer] {message['level']}"
    )
