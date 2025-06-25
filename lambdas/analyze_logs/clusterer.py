# lambda_error_analyzer/lambdas/analyze_logs/clusterer.py
import re
from collections import defaultdict
from typing import List, Dict
import json
import hashlib
from models import LogCluster

# (All constant definitions like _TS, _BRK, _NORM, _LEVEL_RANK remain the same)
_TS    = re.compile(r'^\s*\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?Z?\s*')
_BRK   = re.compile(r'\[(CRITICAL|ERROR|WARNING|INFO|SERVICE|DEBUG)\]', re.I)
_BARE  = re.compile(r'\b(CRITICAL|ERROR|WARNING|INFO|SERVICE|DEBUG)\b', re.I)
_NORM  = [
    (re.compile(r'\b0x[0-9a-fA-F]+\b'), '<hex>'),
    (re.compile(r'\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b', re.I), '<uuid>'),
    (re.compile(r'\b\d+\.\d+\.\d+\.\d+\b'), '<ip>'),
    (re.compile(r'\b\d+\b'), '<num>'),
]
_LEVEL_RANK = {'CRITICAL':4,'ERROR':3,'WARNING':2,'INFO':1,'SERVICE':1,'DEBUG':0}

def _normalise(text: str) -> str:
    for regex, token in _NORM:
        text = regex.sub(token, text)
    return text.strip()

def _first_line(msg: str) -> str:
    if not msg:
        return ""
    return msg.splitlines()[0].strip()

def _hash(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:8]


class ExtractSignature:
    def __init__(self, min_severity="WARNING"):
        self.min_severity = min_severity

    def _extract_signature(self, log_message: str) -> str:
        # 1. Check for JSON logs
        if log_message.lstrip().startswith('{'):
            try:
                js = json.loads(log_message)
                lvl = str(js.get('level', js.get('severity', 'INFO'))).upper()
                
                if _LEVEL_RANK.get(lvl, 0) < _LEVEL_RANK.get(getattr(self, "min_severity", "WARNING"), 2):
                    return ""
                
                msg = js.get('msg') or js.get('message', '')
                return f"{lvl}: {_normalise(msg)}" if msg else f"{lvl}:"

            except Exception:
                pass 

        # 2. Process text logs
        line = _first_line(log_message)
        line = _TS.sub('', line).strip()

        m = _BRK.search(line) or _BARE.search(line)
        if m:
            level = m.group(1).upper()
            if _LEVEL_RANK.get(level, 0) < _LEVEL_RANK.get(getattr(self, "min_severity", "WARNING"), 2):
                return ""
            
            msg_start = m.end()
            candidate = line[msg_start:].lstrip(":- ").strip()

            # --- MODIFIED LOGIC ---
            # Generalize the check for a trailing JSON object
            # This looks for "Details: {..." or just a JSON blob at the end.
            json_match = re.search(r'(?:Details:)?\s*(\{.*\})$', candidate)
            if json_match:
                json_part = json_match.group(1)
                # Check if it's a valid JSON to avoid false positives
                try:
                    json.loads(json_part)
                    # Get the text part before the JSON
                    main_message_part = candidate[:json_match.start()].strip()
                    # Return ONLY the main message part, discarding the JSON
                    return f"{level}: {_normalise(main_message_part)}"
                except json.JSONDecodeError:
                    # Not a valid JSON, so we fall through and normalize the whole thing
                    pass
            # --- END OF MODIFICATION ---
            
            exc_match = re.search(r'\b(\w+(Exception|Error))\b[^:]*:? (.+)', candidate)
            if exc_match:
                   return _normalise(f"{level}: {exc_match.group(1)} {exc_match.group(3)}")

            return _normalise(f"{level}: {candidate}") if candidate else f"{level}"
        
        # 3. Handle unclassified logs
        return f"UNCLASSIFIED:{_hash(_normalise(line))}"



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
        if not log_message.strip():
            return ""
        return ExtractSignature(min_severity="DEBUG")._extract_signature(log_message)

