# lambda_error_analyzer/lambdas/analyze_logs/clusterer.py
import re
from collections import defaultdict
from typing import List, Dict
import json
import hashlib
from models import LogCluster
from parser import ExtractSignature
from datetime import datetime, timezone

class LogClusterer:
    """
    Groups raw log strings into clusters based on a list of regex patterns.
    The core logic of this class is independent of the summarization service and remains unchanged.
    """

    def __init__(self, patterns: List[str]):
        """
        Initializes the clusterer with a list of regex patterns.

        Args:
            patterns (List[str]): A list of regex strings used to find the "signature" line in a log.
        """
        # Compile regex patterns for efficiency
        self.signature_patterns = [re.compile(p, re.MULTILINE) for p in patterns]

    def cluster_logs(self, raw_logs: List[str]) -> List[Dict]:
        """
        Processes a list of raw log strings and groups them into LogCluster objects.
        """
        timestamps: Dict[str, List[str]] = defaultdict(list)
        representative_logs: Dict[str, str] = defaultdict(list)

        extractor = ExtractSignature(min_severity="WARNING")
        for log in raw_logs:
            if not log.strip():
                continue
            result = extractor.extract(log)
            ts = result["timestamp"]
            signature = result["signature"]
            if not signature:
                continue
            # Only cluster logs that have a valid signature
            if signature:
                timestamps[signature].append(ts)
                representative_logs[signature] = log
        print(f"Clusters extracted: {json.dumps(timestamps)}")
        log_cluster_list = []
        for signature, grouped_timestamps in timestamps.items():
            cluster = {
                "signature": signature,
                "count": len(grouped_timestamps),
                "representative_log": representative_logs[signature],
                "timestamps": grouped_timestamps
            }
            log_cluster_list.append(cluster)
        
        # Sort clusters by importance in descending order for clarity
        return sorted(log_cluster_list, key=lambda c: c["count"], reverse=True)

    # def extract_signature(self, log_message: str) -> str:
    #     """
    #     Extracts a stable signature from a log message.
    #     1. Handles common bracketed log levels like [ERROR], [CRITICAL].
    #     2. Falls back to user-supplied regex patterns for more complex cases.
    #     """
    #     if not log_message.strip():
    #         return ""
    #     return ExtractSignature(min_severity="DEBUG")._extract_signature(log_message)

