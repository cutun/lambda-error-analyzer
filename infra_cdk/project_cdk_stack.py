from aws_cdk import (
    Stack,
    Duration,
    CfnParameter,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_lambda as _lambda,
    aws_lambda_event_sources as lambda_event_sources,
    aws_s3 as s3,
    aws_s3_notifications as s3_nots,
    aws_sns as sns,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as apigw_integrations,
    aws_iam as iam,
    CfnOutput
)
from constructs import Construct

class ProjectCdkStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # === Parameters for Deployment ===
        sender_email_param = CfnParameter(self, "VerifiedSenderEmail", type="String",
            description="The email address verified with SES to send alerts from.")
        
        recipient_email_param = CfnParameter(self, "RecipientEmail", type="String",
            description="A comma-separated list of email addresses that will receive alerts.")
            
        slack_param_name = CfnParameter(self, "SlackWebhookSsmParamName", type="String",
            description="The name of the SSM Parameter that stores the Slack Webhook URL.")

        # === Define a Shared Lambda Layer ===
        common_layer = _lambda.LayerVersion(self, "CommonLayer",
            code=_lambda.Code.from_asset("lambda_layer"),
            compatible_runtimes=[_lambda.Runtime.PYTHON_3_12],
            description="A shared layer for the lambdas"
        )

        # === STAGE 1: Ingestion ===
        raw_logs_bucket = s3.Bucket(self, "RawLogBucket",
            removal_policy=RemovalPolicy.DESTROY, # Automatically delete the bucket when the stack is destroyed 
            auto_delete_objects=True,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, # Block public access to the bucket
            versioned=True,  # Enable versioning to keep track of changes
            encryption=s3.BucketEncryption.S3_MANAGED,  # Enable server-side encryption
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_PREFERRED,  # Ensure bucket owner has full control
            # Lifecycle rules to manage log retention
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="LogRetention",
                    enabled=True,
                    expiration=s3.Duration.days(30),  # Automatically delete objects after 30 days
                )
            ]
        )  
        
        ingest_log_function = _lambda.Function(self, "IngestLogFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("lambdas/ingest_log"),
            handler="app.handler",
            environment={"RAW_LOGS_BUCKET_NAME": raw_logs_bucket.bucket_name},
            layers=[common_layer]
        )
        raw_logs_bucket.grant_write(ingest_log_function)
        
        http_api = apigw.HttpApi(self, "LogIngestionApi",
            default_integration=apigw_integrations.HttpLambdaIntegration("IngestionIntegration", handler=ingest_log_function)
        )

        # === STAGE 2: Analysis ===
        log_table = dynamodb.Table(self, "LogTable",
            partition_key=dynamodb.Attribute(name="analysis_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            stream=dynamodb.StreamViewType.NEW_IMAGE,
            time_to_live_attribute="ttl_expiry",
        )
        
        analyze_log_function = _lambda.Function(self, "AnalyzeLogFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("lambdas/analyze_logs"),
            handler="app.handler",
            timeout=Duration.seconds(30),
            environment={
                "DYNAMODB_TABLE_NAME": log_table.table_name,
                "BEDROCK_MODEL_ID": "amazon.nova-micro-v1:0"
            },
            layers=[common_layer]
        )
        log_table.grant_write_data(analyze_log_function)
        raw_logs_bucket.grant_read(analyze_log_function)
        analyze_log_function.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"]))
        analyze_log_function.add_event_source(lambda_event_sources.S3EventSource(raw_logs_bucket, events=[s3.EventType.OBJECT_CREATED]))

        # === STAGE 3: Filtering ===
        final_alerts_topic = sns.Topic(self, "FinalAlertsTopic")

        filter_alert_function = _lambda.Function(self, "FilterAlertFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("lambdas/filter_alert"),
            handler="app.handler",
            environment={"FINAL_ALERTS_TOPIC_ARN": final_alerts_topic.topic_arn},
            layers=[common_layer]
        )
        final_alerts_topic.grant_publish(filter_alert_function)
        filter_alert_function.add_event_source(lambda_event_sources.DynamoEventSource(log_table, starting_position=_lambda.StartingPosition.LATEST))

        # === STAGE 4: Alerting ===
        send_alert_function = _lambda.Function(self, "SendAlertFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("lambdas/send_alert"),
            handler="app.handler",
            timeout=Duration.seconds(15),
            environment={
                "RECIPIENT_EMAIL": recipient_email_param.value_as_string,
                "SENDER_EMAIL": sender_email_param.value_as_string,
                "SLACK_WEBHOOK_URL": slack_param_name.value_as_string
            },
            layers=[common_layer]
        )
        send_alert_function.add_to_role_policy(iam.PolicyStatement(actions=["ses:SendEmail", "ses:SendRawEmail"], resources=["*"]))
        send_alert_function.add_to_role_policy(iam.PolicyStatement(actions=["ssm:GetParameter"], resources=["*"]))
        send_alert_function.add_event_source(lambda_event_sources.SnsEventSource(final_alerts_topic))
        
        # === Outputs ===
        CfnOutput(self, "ApiEndpointUrl", value=f"{http_api.url}logs")