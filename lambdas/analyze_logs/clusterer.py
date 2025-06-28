# lambda_error_analyzer/lambdas/analyze_logs/clusterer.py
import re
from collections import defaultdict
from typing import List, Dict, Any
from datetime import datetime

# Import from lambda layer
from parser import ExtractSignature

class LogClusterer:
    """
    Groups raw log strings into clusters based on extracted signatures.
    This version relies on a dedicated parser for signature extraction.
    """

    def __init__(self, patterns: List[str] = None):
        """
        Initializes the clusterer. The patterns argument is kept for
        compatibility but is not directly used if the parser handles everything.
        """
        self.extractor = ExtractSignature(min_severity="WARNING")


    def cluster_logs(self, raw_logs: List[str]) -> List[Dict[str, Any]]:
        """
        Processes a list of raw log strings and groups them into cluster
        dictionaries.
        """
        # Use a single dictionary to hold aggregated data for each cluster signature.
        clusters_in_progress: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            "timestamps": [],
            "count": 0,
            "representative_log": "",
            "level_rank": 0 # Default to a low number (low importance)
        })

        for log in raw_logs:
            if not log.strip():
                continue

            result = self.extractor.extract(log)
            if not result or not result.get("signature", "").strip():
                continue

            # Extract data from the parser's result
            signature = result["signature"]
            timestamp = result["timestamp"]
            level_rank = result["level_rank"]
            
            # Get the dictionary for the current signature
            cluster_data = clusters_in_progress[signature]
            
            # Append the timestamp (ensuring it's a string)
            if isinstance(timestamp, datetime):
                timestamp = timestamp.isoformat()
            cluster_data["timestamps"].append(timestamp)
            
            # Increment the count
            cluster_data["count"] += 1

            # Keep the first log as the representative and set the level
            if not cluster_data["representative_log"]:
                cluster_data["representative_log"] = log
                cluster_data["level_rank"] = level_rank

        # Convert the aggregated data into the final list format
        final_clusters = [
            {
                "signature": sig,
                "count": data["count"],
                "level_rank": data["level_rank"],
                "representative_log": data["representative_log"],
                "timestamps": data["timestamps"]
            }
            for sig, data in clusters_in_progress.items()
        ]

        # Sort clusters by occurrence count, descending
        return sorted(final_clusters, key=lambda c: c["count"], reverse=True)
    