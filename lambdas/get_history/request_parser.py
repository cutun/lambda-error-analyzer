# lambdas/get_history/request_parser.py
from datetime import datetime, timedelta, timezone

class InvalidRequestError(ValueError):
    """Custom exception for validation errors."""
    pass

def parse_and_validate_request(event: dict) -> tuple[str, str, int]:
    """
    Parses the API Gateway event, validates query parameters, and returns them.

    Args:
        event: The API Gateway event dictionary.

    Returns:
        A tuple containing the signature, start_time_iso, and hours_lookback.
    
    Raises:
        InvalidRequestError: If validation fails.
    """
    query_params = event.get('queryStringParameters') or {}
    signature = query_params.get('signature')
    
    # Require signature to query
    if not signature:
        raise InvalidRequestError('Missing required query parameter: signature')
        
    try:
        hours_lookback = int(query_params.get('hours', 24))
    except ValueError:
        raise InvalidRequestError('Invalid query parameter: hours must be an integer.')

    # Calculate the start time for the query
    start_time = datetime.now(timezone.utc) - timedelta(hours=hours_lookback)
    start_time_iso = start_time.isoformat()
    
    return signature, start_time_iso, hours_lookback
