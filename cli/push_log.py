import os
import requests
import json
import uuid
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment variables from a .env file for local testing
load_dotenv()

# Get the API Gateway endpoint URL from an environment variable
API_ENDPOINT = os.environ.get("LOG_API")

def create_log_entry_string(log_level, message, details=None) -> str:
    """
    Creates a single log entry as a JSON formatted string.
    """
    if details is None:
        details = {}
    return f"[{datetime.now(timezone.utc).isoformat()}][{log_level.upper()}]: {message} Details: {json.dumps(details)}"

def send_log_batch_to_api(log_batch_string: str):
    """
    Sends a string containing one or more logs to the API.
    """
    if not API_ENDPOINT:
        print("❌ ERROR: LOG_API environment variable not set. Please create a .env file.")
        return

    print("--- Attempting to send log batch ---")
    print(log_batch_string)
    print("------------------------------------")
    
    try:
        # Send the raw string as data with the correct Content-Type
        response = requests.post(
            API_ENDPOINT,
            data=log_batch_string.encode('utf-8'), # Encode the string to bytes
            headers={'Content-Type': 'text/plain'},
            timeout=10
        )
        response.raise_for_status()
        print("\n✅ Success! Log batch sent.")
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.json()}")

    except requests.exceptions.RequestException as e:
        print(f"\n❌ Failed to send log batch.")
        print(f"Error: {e}")

if __name__ == "__main__":
    print("--- Log Analyzer Test CLI ---")

    # 1. Create a list of individual log strings
    log1 = create_log_entry_string(
        "CRITICAL",
        "NullPointerException in user_authentication.py",
        {"service": "auth-service", "line": 152}
    )
    log2 = create_log_entry_string(
        "CRITICAL",
        "Database connection failed: timeout expired.",
        {"service": "db-connector", "retry_attempts": 3}
    )
    log3 = create_log_entry_string(
        "WARNING",
        "API response time exceeded threshold.",
        {"service": "billing-api", "response_ms": 2500}
    )

    # 2. Join the logs together with a double newline, just as the analyzer expects
    log_batch = f"{log1}\n\n{log2}\n\n{log3}"
    
    # 3. Send the complete batch to the API
    send_log_batch_to_api(log_batch)
