import os
import requests
import argparse
from dotenv import load_dotenv
import random

# Load environment variables from a .env file for local testing
load_dotenv()

# Get the API Gateway endpoint URL from an environment variable
API_ENDPOINT = os.environ.get("LOG_API")

def send_log_file_to_api(file_path: str, amount: int):
    """
    Reads the first 500 lines of a log file and sends it to the API endpoint.
    """
    if not API_ENDPOINT:
        print("❌ ERROR: LOG_API environment variable not set. Please create a .env file.")
        return

    try:
        print(f"--- Reading log file: {file_path} ---")
        with open(file_path, 'r', encoding='utf-8') as f:
            log_contents = f.readlines()
        size_limit = amount
        max_lines = 500
        log_content = "\n".join(log_contents[:max_lines])

        # The analyze_log function expects logs to be separated by double newlines.
        # We ensure the content ends this way for compatibility.
        if not log_content.strip():
            print("⚠️ Warning: Log file is empty. Skipping.")
            return
            
        if not log_content.endswith('\n'):
            log_content += '\n'

        print("Attempting to send log batch...")
        
        # Send the raw string as data with a 'text/plain' content type
        response = requests.post(
            API_ENDPOINT,
            data=log_content.encode('utf-8'), # Encode the string to bytes
            headers={'Content-Type': 'text/plain'},
            timeout=1000
        )
        response.raise_for_status() # Raise an exception for bad status codes
        
        print("\n✅ Success! Log batch sent.")
        print(f"Status Code: {response.status_code}")
        print(f"Response Body: {response.json()}")

    except FileNotFoundError:
        print(f"❌ ERROR: File not found at path: {file_path}")
    except requests.exceptions.RequestException as e:
        print(f"\n❌ Failed to send log batch.")
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")


if __name__ == "__main__":
    # --- Set up the command-line argument parser ---
    parser = argparse.ArgumentParser(
        description="Reads log files and sends their content to the Log Analyzer API."
    )
    # This defines a required argument that can accept one or more file paths
    parser.add_argument(
        'log_files',
        metavar='FILE',
        type=str,
        nargs='+',
        help='One or more paths to the .log files to be sent.'
    )

    args = parser.parse_args()

    # Loop through all the file paths provided and send each one, choose 100 random log from each
    for file_path in args.log_files:
        send_log_file_to_api(file_path, 100)
