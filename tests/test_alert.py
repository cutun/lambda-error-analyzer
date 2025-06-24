from boto3.dynamodb.types import TypeDeserializer
import json
def unmarshall_dynamodb_item(ddb_item: dict) -> dict:
    """
    Converts a DynamoDB-formatted item into a regular Python dictionary.
    """
    # Create an instance of the deserializer
    class customDeserializer(TypeDeserializer):
        def _deserialize_n(self, value):
            return int(value)
        
    deserializer = customDeserializer()

    # Use a dictionary comprehension to apply the deserializer to every item
    return {k: deserializer.deserialize(v) for k, v in ddb_item.items()}



sample = {
            "summary": {
                "S": "Error communicating with Bedrock API: An error occurred (ValidationException) when calling the InvokeModel operation: Invocation of model ID amazon.nova-micro-v1:0 with on-demand throughput isn’t supported. Retry your request with the ID or ARN of an inference profile that contains this model."
            },
            "total_logs_processed": {
                "N": "3"
            },
            "total_clusters_found": {
                "N": "2"
            },
            "ttl_expiry": {
                "N": "1750917290"
            },
            "analysis_id": {
                "S": "24989be7-069e-4d1f-8425-2367af832632"
            },
            "clusters": {
                "L": [
                    {
                        "M": {
                            "signature": {
                                "S": "T05:54:45."
                            },
                            "count": {
                                "N": "2"
                            },
                            "log_samples": {
                                "L": [
                                    {
                                        "S": "[2025-06-24T05:54:45.020090+00:00][CRITICAL]: NullPointerException in user_authentication.py Details: {\"service\": \"auth-service\", \"line\": 152}"
                                    },
                                    {
                                        "S": "[2025-06-24T05:54:45.020090+00:00][CRITICAL]: Database connection failed: timeout expired. Details: {\"service\": \"db-connector\", \"retry_attempts\": 3}"
                                    }
                                ]
                            },
                            "is_recurring": {
                                "BOOL": True
                            },
                            "representative_log": {
                                "S": "[2025-06-24T05:54:45.020090+00:00][CRITICAL]: NullPointerException in user_authentication.py Details: {\"service\": \"auth-service\", \"line\": 152}"
                            }
                        }
                    },
                    {
                        "M": {
                            "signature": {
                                "S": "4T05:54:45."
                            },
                            "count": {
                                "N": "1"
                            },
                            "log_samples": {
                                "L": [
                                    {
                                        "S": "[2025-06-24T05:54:45.020090+00:00][WARNING]: API response time exceeded threshold. Details: {\"service\": \"billing-api\", \"response_ms\": 2500}"
                                    }
                                ]
                            },
                            "is_recurring": {
                                "BOOL": True
                            },
                            "representative_log": {
                                "S": "[2025-06-24T05:54:45.020090+00:00][WARNING]: API response time exceeded threshold. Details: {\"service\": \"billing-api\", \"response_ms\": 2500}"
                            }
                        }
                    }
                ]
            }
        }
        
if __name__ == "__main__":
    print(unmarshall_dynamodb_item(sample))