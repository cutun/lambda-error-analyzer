# Lambda Error Analyzer

## Project Overview
This is a serverless error logging and analysis system built with AWS Lambda, S3, and DynamoDB. The system captures logs from different services or devices, stores them in the cloud, and triggers alerts or insights based on error patterns.

## Features
- Automatically ingest error logs via API (using AWS API Gateway)
- Store logs in DynamoDB or S3
- Analyze logs for recurring error types or critical failures
- Send email/SMS alerts using AWS SNS
- Serverless architecture using AWS Lambda (no backend server management)

## Tech Stack
- AWS Lambda (Python)
- Amazon API Gateway
- Amazon S3
- Amazon DynamoDB
- AWS SNS (for alerts)
- CloudWatch (for logging & metrics)

## Use Cases
- Monitor application health in real-time
- Detect recurring issues or exceptions
- Receive instant alerts for high-severity errors

## How It Works
1. Logs are POSTed to an API Gateway endpoint
2. API Gateway triggers a Lambda function
3. Lambda stores logs in S3/DynamoDB
4. If critical errors are found, another Lambda sends an alert via SNS
5. A separate Lambda function runs periodically to analyze trends

## Status
Project planning complete  
Development in progress

## Team
- Minh Tran
- Eric Wang
- Hunter Chan
