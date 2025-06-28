# lambda_error_analyzer/lambdas/analyze_logs/models.py
"""
Plain-dataclass models and a simple settings class for the Log Analyzer.
"""
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List


class AppSettings:
    """
    Loads configuration settings directly from environment variables,
    providing sensible defaults for local testing.
    """
    def __init__(self):
        self.aws_region: str = os.getenv("AWS_REGION", "us-east-1")
        self.log_bucket: str = os.getenv("LOG_BUCKET", "dummy-log-bucket")
        self.dynamodb_table_name: str = os.getenv("DYNAMODB_TABLE_NAME", "LogAnalysisResults")
        self.error_state_table_name: str = os.getenv("ERROR_STATE_TABLE_NAME", "LogErrorStates")
        self.sns_topic_arn: str = os.getenv(
            "SNS_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:DummyTopic"
        )
        self.bedrock_model_id: str = os.getenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0")
        
        # Thresholds
        self.recurrence_count_threshold: int = int(os.getenv("RECURRENCE_COUNT_THRESHOLD", "5"))
        self.recurrence_time_window_seconds: int = int(os.getenv("RECURRENCE_TIME_WINDOW_SECONDS", "3600"))
        self.default_baseline_rate_per_hour: float = float(os.getenv("DEFAULT_BASELINE_RATE_PER_HOUR", "0.1"))

# Create a single, shared instance to be imported by other modules.
settings = AppSettings()

# Data models
@dataclass
class LogCluster:
    """
    Represents a cluster of similar log messages.
    This is a pure data container without extra methods.
    """
    signature: str
    count: int
    log_samples: List[str]
    representative_log: str
    is_recurring: bool = False
    anomaly_score: float = 0.0

@dataclass
class LogAnalysisResult:
    """
    Represents the final JSON structure produced by the analyzer.
    This is a pure data container without extra methods.
    """
    analysis_id: str
    summary: str
    total_logs_processed: int
    total_clusters_found: int
    clusters: List[LogCluster]
    # The default_factory ensures a new UTC timestamp is created for each instance.
    processed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    # A constant value used as the partition key for the sorting index.
    gsi1pk: str = "ANALYSIS_RESULT"
