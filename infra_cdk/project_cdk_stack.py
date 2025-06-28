# infra_cdk/project_cdk_stack.py
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
    aws_s3_deployment as s3_deployment,
    aws_sns as sns,
    aws_apigatewayv2 as apigw,
    aws_apigatewayv2_integrations as apigw_integrations,
    aws_kinesisfirehose as firehose,
    aws_iam as iam,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_apigatewayv2 as apigw,
    CfnOutput
)
from constructs import Construct

class ProjectStack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # === Parameters for Deployment ===
        sender_email_param = CfnParameter(self, "VerifiedSenderEmail", type="String",
            description="The email address verified with SES to send alerts from.")
        
        recipient_email_param = CfnParameter(self, "RecipientEmail", type="String",
            description="A comma-separated list of email addresses that will receive alerts.")
            
        slack_param_name = CfnParameter(self, "SlackWebhookSsmParamName", type="String",
            description="The name of the SSM Parameter that stores the Slack Webhook URL.")
        
        # === Frontend Deployment to S3 ===

        # 1. Create a private S3 bucket
        frontend_bucket = s3.Bucket(self, "FrontendBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL, # Keep it private
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # 2. Create a CloudFront Origin Access Identity (OAI)
        origin_access_identity = cloudfront.OriginAccessIdentity(self, "MyOAI")
        frontend_bucket.grant_read(origin_access_identity) # Allow OAI to read from the bucket

        # 3. Create a CloudFront distribution
        distribution = cloudfront.Distribution(self, "CloudFrontDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3Origin(
                    frontend_bucket,
                    origin_access_identity=origin_access_identity # Pass the OAI to the origin
                ),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS
            ),
            default_root_object="index.html",
        )

        # 4. Define the deployment from your local `frontend` folder
        s3_deployment.BucketDeployment(self, "DeployStaticWebsite",
            sources=[s3_deployment.Source.asset("./frontend")],
            destination_bucket=frontend_bucket,
            distribution=distribution,
            distribution_paths=["/*"],
        )

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
            # Increase the buffering size to accommodate large files
            buffering_size=Size.mebibytes(128) 
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
            default_integration=apigw_integrations.HttpLambdaIntegration("IngestionIntegration", handler=ingest_log_function),
            cors_preflight={
                "allow_headers": ["Content-Type"],
                "allow_methods": [
                    apigw.CorsHttpMethod.GET,
                    apigw.CorsHttpMethod.POST,
                    apigw.CorsHttpMethod.OPTIONS
                ],
                "allow_origins": [f"https://{distribution.distribution_domain_name}"],
            }
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
            timeout=Duration.minutes(5),
            environment={
                "DYNAMODB_TABLE_NAME": analysis_results_table.table_name,
                "BEDROCK_MODEL_ID": "amazon.nova-micro-v1:0"
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
            timeout=Duration.minutes(10),
            environment={
                "FINAL_ALERTS_TOPIC_ARN": final_alerts_topic.topic_arn,
                "HISTORY_TABLE_NAME": log_history_table.table_name
            },
            memory_size=2048,
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

        # === FRONTEND: History API ===
        get_history_function = _lambda.Function(self, "GetHistoryFunction",
            runtime=_lambda.Runtime.PYTHON_3_12,
            code=_lambda.Code.from_asset("lambdas/get_history"),
            handler="app.handler",
            environment={
                "HISTORY_TABLE_NAME": log_history_table.table_name
            },
            layers=[common_layer]
        )
        log_history_table.grant_read_data(get_history_function)
        history_integration = apigw_integrations.HttpLambdaIntegration(
            "HistoryIntegration",
            handler=get_history_function
        )
        
        http_api.add_routes(
            path="/history",
            methods=[apigw.HttpMethod.GET],
            integration=history_integration
        )

        # === Outputs ===
        CfnOutput(self, "ApiIngestionEndpointUrl", value=f"{http_api.url}logs", description="The URL to post logs to.")
        CfnOutput(self, "ApiHistoryEndpointUrl", value=f"{http_api.url}history", description="The URL to get error history from.")
        CfnOutput(self, "FrontendURL",
            value=f"https://{distribution.distribution_domain_name}",
            description="The live URL for the frontend application."
        )
        

