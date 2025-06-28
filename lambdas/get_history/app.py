# lambdas/get_history/app.py
import os
import json

# Import the refactored sub-modules
from request_parser import parse_and_validate_request, InvalidRequestError
from database_querier import get_occurrence_count

ALLOWED_ORIGIN = os.environ.get("ALLOWED_ORIGIN", "*") # Default to wildcard for safety

def build_response(status_code: int, body: dict) -> dict:
    """Helper function to build the API Gateway proxy response."""
    return {
        'statusCode': status_code,
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': ALLOWED_ORIGIN
        },
        'body': json.dumps(body)
    }

def handler(event: dict, context: object) -> dict:
    """
    API Gateway handler to fetch the history for a specific error signature.
    Orchestrates parsing, querying, and responding by calling sub-modules.
    """
    print(f"Received event: {json.dumps(event)}")
    
    try:
        # --- 1. Parse and Validate Input ---
        signature, start_time_iso, hours_lookback = parse_and_validate_request(event)

        # --- 2. Query the Database ---
        error_count = get_occurrence_count(signature, start_time_iso)
        print(f"Found {error_count} occurrences in the last {hours_lookback} hours.")
        
        # --- 3. Build the Success Response ---
        result_body = {
            'signature': signature,
            'lookback_hours': hours_lookback,
            'occurrence_count': error_count
        }
        return build_response(200, result_body)

    except InvalidRequestError as e:
        print(f"Validation Error: {e}")
        return build_response(400, {'message': str(e)})

    except Exception as e:
        print(f"Internal Server Error: {e}")
        # It's good practice to not expose internal error details to the client
        return build_response(500, {'message': 'An internal server error occurred.'})
