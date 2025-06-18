# cli/push_log.py
import requests
import json
import uuid
from datetime import datetime, timezone

# No API Gateway yet
API_ENDPOINT = "https://webhook.site/9b4f69af-7a01-4bce-9f52-fe2681e56ce6"

def create_log_payload(log_level, message, details=None):
    """
    Creates the dictionary for the log payload.
    This is pure logic and easy to test.
    """
    if details is None: details = {}

    return {
        "log_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": log_level,
        "message": message,
        "details": details
    }

def send_log_to_api(payload):
    """
    Sends a pre-formatted payload to the API.
    This is the part that handles the network request.
    """
    print("Attempting to send log:")
    print(json.dumps(payload, indent=2))
    try:
        response = requests.post(API_ENDPOINT, json=payload, timeout=10)
        response.raise_for_status()
        print("\n✅ Success! Log sent.")
        print(f"Status Code: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Failed to send log (this is expected until the API is deployed).")
        print(f"Error: {e}")

if __name__ == "__main__":
    print("--- Log Analyzer Test CLI ---")
    # Create the test payload
    log_to_send = create_log_payload(
        "TEST",
        "NullPointerException in user_authentication.py",
        {"service": "auth-service", "line": 152}
    )
    # Send it to the API
    send_log_to_api(log_to_send)