import os
import requests
import argparse
from dotenv import load_dotenv
import json
import time

# Load environment variables from a .env file for local testing
load_dotenv()

# Get the API Gateway endpoint URL from an environment variable
API_ENDPOINT = os.environ.get("LOG_API")

def send_log_file_in_batches(file_path: str, batch_size: int = 10000):
    """
    Reads a log file and sends its content to the API endpoint in batches.
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
        # Ceiling division to calculate the total number of batches
        num_batches = (total_lines + batch_size - 1) // batch_size

        print(f"Total lines: {total_lines}. Preparing to send in {num_batches} batch(es) of up to {batch_size} lines each.")

        for i in range(num_batches):
            start_time = time.time()
            batch_num = i + 1
            print(f"\n--- Processing batch {batch_num}/{num_batches} ---")
            
            start_index = i * batch_size
            end_index = start_index + batch_size
            batch_lines = log_contents[start_index:end_index]
            
            # Reconstruct the log content for the current batch.
            # "".join is used because readlines() preserves trailing newlines,
            # correctly reconstructing the original text block.
            log_content = "".join(batch_lines)

            if not log_content.strip():
                print(f"⚠️ Warning: Batch {batch_num} is empty. Skipping.")
                continue

            try:
                print(f"Attempting to send log batch {batch_num}/{num_batches} ({len(batch_lines)} lines)...")
                
                response = requests.post(
                    API_ENDPOINT,
                    data=log_content.encode('utf-8'),
                    headers={'Content-Type': 'text/plain'},
                    timeout=30 # Timeout per batch request
                )
                response.raise_for_status()
                
                print(f"✅ Success! Log batch {batch_num} sent.")
                print(f"Status Code: {response.status_code}")
                try:
                    # Attempt to parse and print JSON response body
                    print(f"Response Body: {response.json()}")
                except json.JSONDecodeError:
                    # Fallback for non-JSON responses
                    print(f"Response Body (not JSON): {response.text}")

            except requests.exceptions.RequestException as e:
                print(f"\n❌ Failed to send log batch {batch_num}.")
                print(f"Error: {e}")
                # Optional: decide if you want to stop on failure or continue with the next batch.
                # For now, we will print the error and continue processing other files.
                break # Stop processing this file if a batch fails
            
            # Add a small half-second delay between batches to avoid rate-limiting
            # if batch_num < num_batches:
            #     time.sleep(max(0.5 - (time.time() - start_time), 0))

    except FileNotFoundError:
        print(f"❌ ERROR: File not found at path: {file_path}")
    except Exception as e:
        print(f"An unexpected error occurred while processing the file: {e}")


if __name__ == "__main__":
    # --- Set up the command-line argument parser ---
    parser = argparse.ArgumentParser(
        description="Reads log files and sends their content in batches to the Log Analyzer API."
    )
    parser.add_argument(
        'log_files',
        metavar='FILE',
        type=str,
        nargs='+',
        help='One or more paths to the .log files to be sent.'
    )

    args = parser.parse_args()

    # Loop through all the file paths provided and send each one
    for file_path in args.log_files:
        send_log_file_in_batches(file_path)
