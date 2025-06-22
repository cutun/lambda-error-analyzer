from aws_cdk import (
    RemovalPolicy,
    Stack,
    aws_iam as iam,
    Aspects,
    aws_dynamodb as ddb, 
    aws_lambda as _lambda, 
    aws_api_gateway as apigw,
    aws_sns as sns,
    aws_sns_subscriptions as sns_subscriptions,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda_event_sources as lambda_event_sources,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cloudwatch_actions,   
    CfnOutput
)

from constructs import Construct
from aws_cdk import Duration, aws_s3 as s3
from cdk_nag import AwsSolutionsChecks

class IngestionApiStack(Stack):
    ''' 
    CDK stack for the ingestion API
    This stack creates an API Gateway with a Lambda function that can be triggered by S3 events or EventBridge schedules.
    The Lambda function processes log batches, clusters recurring stack traces, calls OpenAI for summarization, stores results in DynamoDB, and emits alerts via SNS if needed.
    The stack also includes an S3 bucket for storing logs and a DynamoDB table for storing results.
    The API Gateway is configured to allow CORS and has a single POST method for triggering the ingestion process.
    '''

    def __init__(self, scope: Construct, id: str, **kwargs) -> None:
        super().__init__(scope, id, **kwargs)

        # Create an S3 bucket for logs
        self.log_bucket = s3.Bucket(self, "RawLogBucket",
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

        # Create a DynamoDB table for storing results
        self.results_table = ddb.Table(self, "ResultsTable",
            partition_key=ddb.Attribute(name="id", type=ddb.AttributeType.STRING),  
            sort_key=ddb.Attribute(name="timestamp", type=ddb.AttributeType.STRING),
            billing_mode=ddb.BillingMode.PAY_PER_REQUEST,  # Use on-demand billing mode
            point_in_time_recovery=True,  
        )

        # Create a Lambda function for storing logs
        self.ingest_lambda = _lambda.Function(self, "IngestLambda",
            runtime=_lambda.Runtime.PYTHON_3_8,
            handler="ingest_log.handler", # The handler function in the Lambda code
            code=_lambda.Code.from_asset("lambda/ingest_log"),  
            environment={
                "LOG_BUCKET": self.log_bucket.bucket_name,
                "RESULTS_TABLE": self.results_table.table_name,
            },
            memory_size=1024,  # Set memory size for the Lambda function
            timeout=Duration.minutes(1),  # Set timeout for the Lambda function
        )

        # Grant the Lambda function permissions to store logs in the s3 bucket 
        self.log_bucket.grant_put(self.ingest_lambda)

        # Create an API Gateway for the Lambda function
        self.api = apigw.LambdaRestApi(self, "IngestionApi",
            handler=self.ingest_lambda,
            proxy=False,
            default_cors_preflight_options={ # Configure CORS for the API Gateway
                "allow_origins": apigw.Cors.ALL_ORIGINS,
                "allow_methods": apigw.Cors.ALL_METHODS,
                "allow_headers": apigw.Cors.DEFAULT_HEADERS,
            }
        )

        # Add a POST method to the API Gateway
        ingestion_resource = self.api.root.add_resource("ingest")
        ingestion_resource.add_method("POST")  # POST /ingest

        # Create a Lambda for processing logs and storing results in DynamoDB
        self.analyze_lambda = _lambda.Function(self, "AnalyzeLambda",
            runtime=_lambda.Runtime.PYTHON_3_8,
            handler="analyze_log.handler",  # The handler function in the Lambda code
            code=_lambda.Code.from_asset("lambda/analyze_log"),
            environment={
                "RESULTS_TABLE": self.results_table.table_name,
                "OPENAI_API_KEY": "your_openai_api_key",  # Replace with your OpenAI API key
            }, 
            memory_size=1024,  # Set memory size for the Lambda function
            timeout=Duration.minutes(1),  # Set timeout for the Lambda function
        )

        # Grant the analyze Lambda function permissions to read from the S3 bucket and write to the DynamoDB table
        self.log_bucket.grant_read(self.analyze_lambda)

        # Grant the analyze Lambda function permissions to write to the DynamoDB table
        self.analyze_lambda.add_to_role_policy(iam.PolicyStatement(
            actions=["dynamodb:PutItem","dynamodb:BatchWriteItem"],
            resources=[self.results_table.table_arn]
        ))

        # Add an event source to the analyze Lambda function to trigger it when new objects are created in the S3 bucket
        self.analyze_lambda.add_event_source(lambda_event_sources.S3EventSource(
            self.log_bucket,
            events=[s3.EventType.OBJECT_CREATED],  # Trigger on object creation events
            filters=[s3.NotificationKeyFilter(suffix=".log")]  # Only trigger for .log files
        )
        )

        # Create an SNS topic for alerts
        self.alert_topic = sns.Topic(self, "AlertTopic", display_name="Lambda Error Alerts")

        # Create a Lambda for sending alerts 
        self.alert_lambda = _lambda.Function(self, "AlertLambda",
            runtime=_lambda.Runtime.PYTHON_3_8,
            handler="send_alert.handler",  # The handler function in the Lambda code
            code=_lambda.Code.from_asset("lambda/send_alert"),
            environment={
                "ALERT_TOPIC": self.alert_topic.topic_arn,
                "RESULTS_TABLE": self.results_table.table_name,
            },
            memory_size=512,  # Set memory size for the Lambda function
            timeout=Duration.minutes(1),  # Set timeout for the Lambda function
        )

        # Grant the alert Lambda function permissions to publish to the SNS topic
        self.alert_topic.grant_publish(self.alert_lambda)  

        # Grant the alert Lambda function permissions to read from the DynamoDB table
        self.results_table.grant_read_data(self.alert_lambda)
    
        # Subscribe the alert Lambda function to the SNS topic
        self.alert_topic.add_subscription(sns_subscriptions.LambdaSubscription(self.alert_lambda))

        # Add an EventBridge rule to trigger the Lambda function on a schedule
        self.schedule_rule = events.Rule(self, "ScheduleRule",
            schedule=events.Schedule.cron(minute="0", hour="12"),  # Trigger every day at noon
        )
    
        # Add the alert Lambda function as a target of the EventBridge rule
        self.schedule_rule.add_target(targets.LambdaFunction(self.alert_lambda))

        # Create a CloudWatch alarm for the ingest Lambda function to monitor errors
        self.lambda_error_alarm = cloudwatch.Alarm(self, "LambdaErrorAlarm",
            metric=self.ingest_lambda.metric_errors(),
            threshold=1,  # Trigger the alarm if there is at least one error
            evaluation_periods=1,  # Evaluate the metric for one period
            datapoints_to_alarm=1,  # Trigger the alarm if one data point is in the alarm state
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
        )

        # Add an action to the CloudWatch alarm to publish to the SNS topic
        self.lambda_error_alarm.add_alarm_action(cloudwatch_actions.SnsAction(self.alert_topic))

        # Output the API endpoint URL
        self.api_url = self.api.url_for_path("/ingest")

        # Output the stack resources
        CfnOutput(self, "ApiUrl", value=self.api.url_for_path("/ingest"))
        CfnOutput(self, "LogBucketName", value=self.log_bucket.bucket_name)
        CfnOutput(self, "ResultsTableName", value=self.results_table.table_name)
        CfnOutput(self, "AlertTopicArn", value=self.alert_topic.topic_arn)
        CfnOutput(self, "IngestLambdaArn", value=self.ingest_lambda.function_arn)
        CfnOutput(self, "AnalyzeLambdaArn", value=self.analyze_lambda.function_arn)
        CfnOutput(self, "AlertLambdaArn", value=self.alert_lambda.function_arn)
        CfnOutput(self, "ScheduleRuleArn", value=self.schedule_rule.rule_arn)

        # Create a CloudWatch dashboard for monitoring
        dashboard = cloudwatch.Dashboard(self, "IngestionDashboard",
            dashboard_name="IngestionDashboard"
        )

        # Add widgets to the dashboard
        def lambda_widgets(lambda_fn: _lambda.Function, title_prefix: str) -> list[cloudwatch.GraphWidget]:
            return [
                cloudwatch.GraphWidget(
                    title=f"{title_prefix} Invocations",
                    left=[lambda_fn.metric_invocations()],
                    width=12
                ),
                cloudwatch.GraphWidget(
                    title=f"{title_prefix} Errors",
                    left=[lambda_fn.metric_errors()],
                    width=12
                )
            ]
        
        dashboard.add_widgets(
            *lambda_widgets(self.ingest_lambda, "Ingest Lambda"),
            *lambda_widgets(self.analyze_lambda, "Analyze Lambda"),
            *lambda_widgets(self.alert_lambda, "Alert Lambda"),
            cloudwatch.GraphWidget(
                title="S3 Bucket Size",
                left=[self.log_bucket.metric_bucket_size_bytes(storage_type=s3.StorageType.STANDARD_STORAGE)],
                width=12
            ),
            cloudwatch.GraphWidget(
                title="DynamoDB Read Capacity",
                left=[self.results_table.metric_consumed_read_capacity_units()],
                width=12
            ),
            cloudwatch.GraphWidget(
                title="DynamoDB Write Capacity",
                left=[self.results_table.metric_consumed_write_capacity_units()],
                width=12
            )
        )

        # Add lifecycle rules to the S3 bucket to manage log retention
        self.log_bucket.add_lifecycle_rule(
            id="MoveAndExpireLogs",
            enabled=True,
            prefix="",                              
            transitions=[
            s3.Transition(
                storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                transition_after=Duration.days(30)
            ),
            s3.Transition(
                storage_class=s3.StorageClass.GLACIER,
                transition_after=Duration.days(90)
            )
            ],
            expiration=Duration.days(365) # delete after a year in Glacier
        )

        # Add AWS Solutions checks for best practices
        Aspects.of(self).add(AwsSolutionsChecks())
