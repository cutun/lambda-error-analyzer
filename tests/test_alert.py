# tests/test_send_alert_handler.py
import unittest
import os
import json
from unittest.mock import patch, MagicMock
import importlib

# Use importlib to import the module by its string name
send_alert_app = importlib.import_module("lambda.send_alert.app")

# This is a sample event that mimics what SNS sends to a Lambda subscriber.
# The inner "Message" is a JSON string, just like P2's Lambda would create.
SAMPLE_SNS_EVENT = {
    "Records": [
        {
            "Sns": {
                "Timestamp": "2025-06-18T22:30:00.000Z",
                "Message": json.dumps({
                    "level": "TEST",
                    "error_message": "Sample Error Message",
                    "details": {"host": "db.prod.internal"}
                })
            }
        }
    ]
}

class TestSendAlertHandler(unittest.TestCase):

    # This patch intercepts any call to 'boto3.client' within the 'send_alert_app' module.
    # The '@patch.dict' temporarily sets the environment variable for the duration of the test.
    @patch('lambda.send_alert.app.boto3.client')
    @patch.dict(os.environ, {"ALERT_TOPIC": "arn:aws:sns:us-east-1:123456789012:destination-topic-for-alerts"})
    def test_handler_publishes_to_sns(self, mock_boto_client):
        """
        Tests if the handler correctly parses an SNS event and calls sns.publish.
        """
        print("\nRunning test: test_handler_publishes_to_sns...")

        # --- Setup the Mock ---
        # We create a fake SNS client instance that our test can control.
        mock_sns_instance = MagicMock()
        # We tell the mocked boto3.client to return our fake instance when called.
        mock_boto_client.return_value = mock_sns_instance

        # --- Call the function ---
        # We call your actual handler function with the fake SNS event.
        send_alert_app.handler(SAMPLE_SNS_EVENT, None)

        # --- Assert (Verify) the results ---
        # 1. Verify that boto3.client was called once to create an SNS client.
        mock_boto_client.assert_called_once_with("sns")
        print("✅ Verified that boto3.client('sns') was called.")

        # 2. Verify that the 'publish' method on our fake client was called exactly once.
        mock_sns_instance.publish.assert_called_once()
        print("✅ Verified that sns.publish() was called.")

        # 3. (Optional but powerful) Inspect *what* publish was called with.
        # This checks if your code passed the correct arguments to the publish call.
        publish_args = mock_sns_instance.publish.call_args.kwargs
        self.assertEqual(publish_args['TopicArn'], "arn:aws:sns:us-east-1:123456789012:destination-topic-for-alerts")
        self.assertIn("Database connection failed", publish_args['Message'])
        self.assertIn("CRITICAL", publish_args['Subject'])
        print("✅ Verified that sns.publish() was called with the correct arguments.")


if __name__ == '__main__':
    unittest.main()