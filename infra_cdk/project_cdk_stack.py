from aws_cdk import (
    Stack,
    Size,
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
    aws_kinesisfirehose as firehose,
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
        raw_logs_bucket = s3.Bucket(self, "RawLogsBucket", 
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True
        )

        s3_dest = firehose.S3Bucket(
            raw_logs_bucket,
            compression=firehose.Compression.GZIP,
            # Decrease the buffering time (default is 300 seconds)
            buffering_interval=Duration.seconds(60), 
            # Decrease the buffering size (default is 5 MiB)
            buffering_size=Size.mebibytes(1) 
        )

        delivery_stream = firehose.DeliveryStream(self, "RawLogsDeliveryStream",
                destination=s3_dest
        )
        
        ingest_log_function = _lambda.Function(self, "IngestLogFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("lambdas/ingest_log"),
            handler="app.handler",
            environment={"DELIVERY_STREAM": delivery_stream.delivery_stream_name},
            layers=[common_layer]
        )
        
        # raw_logs_bucket.grant_write(ingest_log_function)
        delivery_stream.grant_put_records(ingest_log_function)

        http_api = apigw.HttpApi(self, "LogIngestionApi",
            default_integration=apigw_integrations.HttpLambdaIntegration("IngestionIntegration", handler=ingest_log_function)
        )

        # === STAGE 2: Analysis ===
        analysis_results_table = dynamodb.Table(self, "AnalysisResultsTable",
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
                "DYNAMODB_TABLE_NAME": analysis_results_table.table_name,
                "BEDROCK_MODEL_ID": "amazon.titan-text-express-v1"
            },
            memory_size=512,
            layers=[common_layer]
        )
        analysis_results_table.grant_write_data(analyze_log_function)
        raw_logs_bucket.grant_read(analyze_log_function)
        analyze_log_function.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"]))
        analyze_log_function.add_event_source(lambda_event_sources.S3EventSource(raw_logs_bucket, events=[s3.EventType.OBJECT_CREATED]))

        # === STAGE 3: Filtering ===
        final_alerts_topic = sns.Topic(self, "FinalAlertsTopic")

        log_history_table = dynamodb.Table(self, "LogHistoryTable",
            partition_key=dynamodb.Attribute(name="signature", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
        )

        filter_alert_function = _lambda.Function(self, "FilterAlertFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("lambdas/filter_alert"),
            handler="app.handler",
            timeout=Duration.seconds(20),
            environment={
                "FINAL_ALERTS_TOPIC_ARN": final_alerts_topic.topic_arn,
                "HISTORY_TABLE_NAME": log_history_table.table_name
            },
            memory_size=512,
            layers=[common_layer]
        )
        final_alerts_topic.grant_publish(filter_alert_function)
        log_history_table.grant_read_write_data(filter_alert_function)
        filter_alert_function.add_event_source(lambda_event_sources.DynamoEventSource(
            analysis_results_table, 
            starting_position=_lambda.StartingPosition.LATEST
        ))

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
            memory_size=512,
            layers=[common_layer]
        )
        send_alert_function.add_to_role_policy(iam.PolicyStatement(actions=["ses:SendEmail", "ses:SendRawEmail"], resources=["*"]))
        send_alert_function.add_to_role_policy(iam.PolicyStatement(actions=["ssm:GetParameter"], resources=[
            f"arn:aws:ssm:{self.region}:{self.account}:parameter/{slack_param_name.value_as_string}"
        ]))
        send_alert_function.add_event_source(lambda_event_sources.SnsEventSource(final_alerts_topic))
        
        # === Outputs ===
        CfnOutput(self, "ApiEndpointUrl", value=f"{http_api.url}logs")
        CfnOutput(self, "RawLogsBucketName", value=raw_logs_bucket.bucket_name)
        CfnOutput(self, "AnalysisResultsTableName", value=analysis_results_table.table_name)
        CfnOutput(self, "LogHistoryTableName", value=log_history_table.table_name)
