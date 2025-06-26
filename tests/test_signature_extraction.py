
import sys
import os
import requests
import json
import uuid
from datetime import datetime, timezone


sys.path.insert(0, "C:\\aws-lambda-error-analyzer\\lambda-error-analyzer\\lambda_layer\\python\\lib\\python3.12\\site-packages")
from parser import ExtractSignature, parse_signature
filename = "test_log_variety_50MB.log"
# filename = "sample_logs.txt"
# filename = "test_log_100MB.log"



if __name__ == "__main__":
    log_file = open(f"tests\\sample_logs\\{filename}")
    content = log_file.read()

    signature_extractor = ExtractSignature(min_severity="WARNING")
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
        result = signature_extractor.extract(log)
        if not result:
            continue
        lvl = result['level_rank']
        sig = result['signature']
        lvl_text, msg = parse_signature(sig)
        ts = result['timestamp']
        print("Log ---> ", log)
        print("    Signature ---> ", sig)
        print("    Level -------> ", lvl_text)
        print("    Message------"+"-"*(len(lvl_text)+2)+"> ", msg)
        print("    Timestamp ---> ", ts)
        print("    Severity ----> ", lvl)
        print("-"*80)


