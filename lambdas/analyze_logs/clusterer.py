import re
from collections import defaultdict
from typing import List, Dict

# Assuming models.py is in the same directory
from .models import LogCluster

class LogClusterer:
    """
    Groups raw log strings into clusters based on a list of regex patterns.
    """

    def __init__(self, patterns: List[str]):
        """
        Initializes the clusterer with a list of regex patterns.

        Args:
            patterns (List[str]): A list of regex strings used to find the "signature" line in a log.
        """
        # We compile the regex patterns for efficiency
        self.signature_patterns = [re.compile(p, re.MULTILINE) for p in patterns]

    def cluster_logs(self, raw_logs: List[str]) -> List[LogCluster]:
        """
        Processes a list of raw log strings and groups them into LogCluster objects.
        """
        clusters: Dict[str, List[str]] = defaultdict(list)

        for log in raw_logs:
            signature = self._extract_signature(log)
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

        return log_cluster_list

    def _extract_signature(self, log_message: str) -> str:
        """
        Pull out a stable signature.
        • First handle common bracket-levels ([ERROR]  / [CRITICAL] …).
        • Then fall back to user-supplied regex patterns.
        """
        # 1️⃣  generic extraction
        level_match = re.search(r"\[(CRITICAL|ERROR|WARNING|INFO|DEBUG)]\s+(.*)", log_message)
        if level_match:
            level, message = level_match.groups()

            # Ignore low-severity noise
            if level not in ("CRITICAL", "ERROR", "WARNING"):
                return ""

            # Special-case: `[ERROR] … Error: <detail>` → want the inner "Error: …"
            if level == "ERROR":
                inner = re.search(r"Error:\s+.+", message)
                if inner:
                    return inner.group(0).strip()

            # Generic fallback, e.g. “CRITICAL: Core component …”
            return f"{level}: {message.strip()}"

        # 2️⃣  user-supplied regexes
        for pattern in self.signature_patterns:
            match = pattern.search(log_message)
            if match:
                # Prefer first capture group if it exists
                return (match.group(1) if match.groups() else match.group(0)).strip()

        return ""  # no signature → ignored