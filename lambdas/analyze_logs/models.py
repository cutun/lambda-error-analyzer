# lambda_error_analyzer/lambdas/analyze_logs/models.py
"""
Plain-dataclass models and settings for the Log Analyzer – no pydantic required.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List


@dataclass
class AppSettings:
    """
    Reads configuration from environment variables (with sensible defaults).
    """
    aws_region: str = field(default_factory=lambda: os.getenv("AWS_REGION", "us-east-1"))
    log_bucket: str = field(default_factory=lambda: os.getenv("LOG_BUCKET", "dummy-log-bucket"))
    dynamodb_table_name: str = field(default_factory=lambda: os.getenv("DYNAMODB_TABLE_NAME", "LogAnalysisResults"))
    error_state_table_name: str = field(default_factory=lambda: os.getenv("ERROR_STATE_TABLE_NAME", "LogErrorStates"))
    sns_topic_arn: str = field(default_factory=lambda: os.getenv(
        "SNS_TOPIC_ARN",
        "arn:aws:sns:us-east-1:123456789012:DummyTopic",
    ))

    # Bedrock
    bedrock_model_id: str = field(default_factory=lambda: os.getenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0"))

    # Recurrence / anomaly thresholds
    recurrence_count_threshold: int = field(
        default_factory=lambda: int(os.getenv("RECURRENCE_COUNT_THRESHOLD", 5))
    )
    recurrence_time_window_seconds: int = field(
        default_factory=lambda: int(os.getenv("RECURRENCE_TIME_WINDOW_SECONDS", 3600))
    )
    default_baseline_rate_per_hour: float = field(
        default_factory=lambda: float(os.getenv("DEFAULT_BASELINE_RATE_PER_HOUR", 0.1))
    )

    def to_dict(self) -> dict:          # keeps signature parity with pydantic
        return asdict(self)

    # pydantic-style alias for drop-in use
    dict = to_dict                      


def get_settings() -> AppSettings:
    """Helper to obtain a populated settings object (mirrors the old API)."""
    return AppSettings()

@dataclass
class LogCluster:
    """
    Represents a cluster of similar log messages.
    """
    signature: str
    count: int
    log_samples: List[str]
    representative_log: str
    is_recurring: bool = False
    anomaly_score: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    dict = to_dict                      # pydantic-style accessor


@dataclass
class LogAnalysisResult:
    """
    Final JSON structure produced by the analyzer.
    """
    analysis_id: str
    summary: str
    total_logs_processed: int
    total_clusters_found: int
    clusters: List[LogCluster]
    processed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    gsi1pk: str = "ANALYSIS_RESULT"     # constant (was Literal in pydantic)

    def to_dict(self) -> dict:
        # Convert nested dataclasses as well
        data = asdict(self)
        # Replace datetime with ISO 8601 string for JSON / DynamoDB
        data["processed_at"] = self.processed_at.isoformat()
        return data

    dict = to_dict                      # pydantic-style accessor
    