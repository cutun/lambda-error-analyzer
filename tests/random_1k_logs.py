import os
import requests
import argparse
from dotenv import load_dotenv
import json
import time
import random

# Load environment variables from a .env file for local testing
load_dotenv()

# Get the API Gateway endpoint URL from an environment variable
API_ENDPOINT = os.environ.get("LOG_API")

def send_log_sample_to_api(file_path: str, sample_size: int = 1000):
    """
    Reads a log file, takes a random sample of up to 1000 lines, and sends
    it to the API endpoint in a single batch.
    """
    if not API_ENDPOINT:
        print("❌ ERROR: LOG_API environment variable not set. Please create a .env file.")
        return

    try:
        print(f"--- Reading log file: {file_path} ---")
        with open(file_path, 'r', encoding='utf-8') as f:
            log_contents = f.readlines()

        if not log_contents:
            print("⚠️ Warning: Log file is empty. Skipping.")
            return

        total_lines = len(log_contents)
        
        # If the file has more lines than our sample size, take a random sample.
        # Otherwise, just use all the lines from the file.
        if total_lines > sample_size:
            print(f"Total lines ({total_lines}) exceeds sample size. Taking a random sample of {sample_size} lines.")
            batch_lines = random.sample(log_contents, sample_size)
        else:
            print(f"Total lines ({total_lines}) is within sample size. Using all lines.")
            batch_lines = log_contents
            
        # Reconstruct the log content for the sampled batch.
        log_content = "".join(batch_lines)

        if not log_content.strip():
            print(f"⚠️ Warning: Selected sample is empty. Skipping.")
            return

        try:
            print(f"Attempting to send log sample ({len(batch_lines)} lines)...")
            
            response = requests.post(
                API_ENDPOINT,
                data=log_content.encode('utf-8'),
                headers={'Content-Type': 'text/plain'},
                timeout=30 # Timeout for the request
            )
            response.raise_for_status()
            
            print(f"✅ Success! Log sample sent.")
            print(f"Status Code: {response.status_code}")
            try:
                # Attempt to parse and print JSON response body
                print(f"Response Body: {response.json()}")
            except json.JSONDecodeError:
                # Fallback for non-JSON responses
                print(f"Response Body (not JSON): {response.text}")

        except requests.exceptions.RequestException as e:
            print(f"\n❌ Failed to send log sample.")
            print(f"Error: {e}")

    except FileNotFoundError:
        print(f"❌ ERROR: File not found at path: {file_path}")
    except Exception as e:
        print(f"An unexpected error occurred while processing the file: {e}")


if __name__ == "__main__":
    # --- Set up the command-line argument parser ---
    parser = argparse.ArgumentParser(
        description="Reads log files, takes a random sample of lines, and sends it to the Log Analyzer API."
    )
    parser.add_argument(
        'log_files',
        metavar='FILE',
        type=str,
        nargs='+',
        help='One or more paths to the .log files to be sampled and sent.'
    )

    args = parser.parse_args()

    # Loop through all the file paths provided and send a sample from each one
    for file_path in args.log_files:
        send_log_sample_to_api(file_path)
