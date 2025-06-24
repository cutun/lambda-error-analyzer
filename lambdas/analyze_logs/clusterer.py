# lambda_error_analyzer/lambdas/analyze_logs/clusterer.py
import re
from collections import defaultdict
from typing import List, Dict
import json
import re
import hashlib

_TS    = re.compile(r'^\s*\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?Z?\s*')
_BRK   = re.compile(r'\[(CRITICAL|ERROR|WARNING|INFO|DEBUG)\]', re.I)
_BARE  = re.compile(r'\b(CRITICAL|ERROR|WARNING|INFO|DEBUG)\b', re.I)
_NORM  = [
    (re.compile(r'\b0x[0-9a-fA-F]+\b'), '<hex>'),
    (re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b', re.I), '<uuid>'),
    (re.compile(r'\b\d+\.\d+\.\d+\.\d+\b'), '<ip>'),
    (re.compile(r'\b\d+\b'), '<num>'),
]
_LEVEL_RANK = {'CRITICAL':4,'ERROR':3,'WARNING':2,'INFO':1,'DEBUG':0}

def _normalise(text: str) -> str:
    for regex, token in _NORM:
        text = regex.sub(token, text)
    return text.strip()

def _first_line(msg: str) -> str:
    return msg.splitlines()[0].strip()

def _hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:8]

class ExtractSignature:
    signature_patterns = [_TS, _BRK, _BARE, _NORM, _LEVEL_RANK]
    def _extract_signature(self, log_message: str) -> str:  # type: ignore[override]
        for pat in self.signature_patterns:
            m = pat.search(log_message)
            if m:
                return _normalise(m.group(1) if m.groups() else m.group(0))

        if log_message.lstrip().startswith('{'):
            try:
                js = json.loads(log_message)
                lvl = str(js.get('level', js.get('severity', 'INFO'))).upper()
                if _LEVEL_RANK.get(lvl, 0) < _LEVEL_RANK.get(getattr(self, "min_severity", "WARNING"), 2):
                    return ""
                msg = js.get('error') or js.get('exception') or js.get('msg') or js.get('message', '')
                return f"{lvl}: {_normalise(msg)}" if msg else ""
            except Exception:
                pass  

        line = _first_line(log_message)
        line = _TS.sub('', line)  # strip timestamp if present

        m = _BRK.search(line) or _BARE.search(line)
        if m:
            level = m.group(1).upper()
            if _LEVEL_RANK[level] < _LEVEL_RANK.get(getattr(self, "min_severity", "WARNING"), 2):
                return ""
            msg_start = m.end()
            candidate = line[msg_start:].lstrip(":- ").strip()
            exc_match = re.search(r'\b(\w+(Exception|Error))\b[^:]*:? (.+)', candidate)
            if exc_match:
                return _normalise(f"{level}: {exc_match.group(1)} {exc_match.group(3)}")
            return _normalise(f"{level}: {candidate}") if candidate else f"{level}"
        
        return f"UNCLASSIFIED:{_hash(_normalise(line))}"


<<<<<<< HEAD
=======
# This model is defined in the same directory.
from models import LogCluster
>>>>>>> c59758037a1e2e8d136c953ca7e701f2f01acdca

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

    def cluster_logs(self, raw_logs: List[str]) -> List[dict]:
        """
        Processes a list of raw log strings and groups them into LogCluster objects.
        """
        clusters: Dict[str, List[str]] = defaultdict(list)

        for log in raw_logs:
            signature = self.extract_signature(log)
            # Only cluster logs that have a valid signature
            if signature:
                clusters[signature].append(log)
        print(f"Clusters with extracted signitures: {json.dumps(clusters)}")
        log_cluster_list = []
        for signature, grouped_logs in clusters.items():
            cluster = {
                "signature": signature,
                "count": len(grouped_logs),
                "log_samples": grouped_logs,
                "representative_log": grouped_logs[0],
                "is_recurring": True
            }
            log_cluster_list.append(cluster)
        
        # Sort clusters by count in descending order for clarity
        return sorted(log_cluster_list, key=lambda c: c["count"], reverse=True)

    def extract_signature(self, log_message: str) -> str:
        """
        Extracts a stable signature from a log message.
        1. Handles common bracketed log levels like [ERROR], [CRITICAL].
        2. Falls back to user-supplied regex patterns for more complex cases.
        """
        return ExtractSignature()._extract_signature(log_message)

