# lambda_error_analyzer/lambdas/analyze_logs/clusterer.py
import re
from collections import defaultdict
from typing import List, Dict

# This model is defined in the same directory.
from models import LogCluster

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

    def cluster_logs(self, raw_logs: List[str]) -> List[LogCluster]:
        """
        Processes a list of raw log strings and groups them into LogCluster objects.
        """
        clusters: Dict[str, List[str]] = defaultdict(list)

        for log in raw_logs:
            signature = self._extract_signature(log)
            # Only cluster logs that have a valid signature
            if signature:
                clusters[signature].append(log)

        log_cluster_list = []
        for signature, grouped_logs in clusters.items():
            cluster = LogCluster(
                signature=signature,
                count=len(grouped_logs),
                log_samples=grouped_logs,
                representative_log=grouped_logs[0],
            )
            log_cluster_list.append(cluster)
        
        # Sort clusters by count in descending order for clarity
        return sorted(log_cluster_list, key=lambda c: c.count, reverse=True)

    def _extract_signature(self, log_message: str) -> str:
        """
        Extracts a stable signature from a log message.
        1. Handles common bracketed log levels like [ERROR], [CRITICAL].
        2. Falls back to user-supplied regex patterns for more complex cases.
        """
        # 1. Generic extraction for standard log levels
        level_match = re.search(r"\[(CRITICAL|ERROR|WARNING|INFO|DEBUG)\]\s+(.*)", log_message)
        if level_match:
            level, message = level_match.groups()

            # Ignore low-severity noise
            if level not in ("CRITICAL", "ERROR", "WARNING"):
                return ""

            # For ERROR level, try to find a more specific "Error: <detail>" message
            if level == "ERROR":
                inner_error_match = re.search(r"Error:\s+.+", message)
                if inner_error_match:
                    return inner_error_match.group(0).strip()
            
            # Generic fallback for CRITICAL or other high-severity levels
            return f"{level}: {message.strip()}"

        # 2. Fallback to user-supplied regex patterns
        for pattern in self.signature_patterns:
            match = pattern.search(log_message)
            if match:
                # Prefer the first capture group if it exists, otherwise use the full match
                return (match.group(1) if match.groups() else match.group(0)).strip()
        
        # Return an empty string if no signature can be found
        return ""