
import sys, os
sys.path.insert(0, "C:\\aws-lambda-error-analyzer\\lambda-error-analyzer")
from lambdas.analyze_logs.clusterer import ExtractSignature
from lambdas.send_alert.formatter import parse_signature

filename = "test_log_variety_50MB.log"
# filename = "sample_logs.txt"
# filename = "test_log_100MB.log"



import os
import requests
import json
import uuid
from datetime import datetime, timezone


if __name__ == "__main__":
    log_file = open(f"tests\\sample_logs\\{filename}")
    content = log_file.read()

    signature_extractor = ExtractSignature(min_severity="DEBUG")
    sample_logs = content.replace("\n\n", "\n")
    log_list = sample_logs.split("\n")
    log_list = [
        """[2025-06-25T02:37:12.198126+00:00][CRITICAL]: NullPointerException in user_authentication.py Details: {"service": "auth-service", "line": 152}""",
        """[2025-06-25T02:37:12.198126+00:00][CRITICAL]: Database connection failed: timeout expired. Details: {"service": "db-connector", "retry_attempts": 3}""",
        """[2025-06-25T02:37:12.198126+00:00][WARNING]: API response time exceeded threshold. Details: {"service": "billing-api", "response_ms": 2500}"""
    ] + log_list

    print("----------Extracting and Parsing Signatures----------")
    for log in log_list[:500]:
        if not log.strip():
            continue
        sig = signature_extractor._extract_signature(log)
        lvl, msg = parse_signature(sig)
        combined_msg = f"{lvl}: {msg}"
        print("Log ---> ", log)
        print("    Signature ---> ", sig)
        print("    Level -------> ", lvl)
        print("    Message------"+"-"*(len(lvl)+2)+"> ", msg)
        print("    Combined ----> ", combined_msg)
        print("-"*80)


