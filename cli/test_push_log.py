# cli/test_push_log.py
import unittest
import json

# tests cli/push_log.py
from push_log import create_log_payload 

class TestLogPayloadBuilder(unittest.TestCase):

    def test_payload_structure_and_content(self):
        """
        This test checks if the create_log_payload function
        builds the log dictionary correctly.
        """
        print("\nRunning test: test_payload_structure_and_content...")
        
        # 1. Define the inputs
        level = "CRITICAL"
        message = "Database connection timed out."
        details = {"host": "db.prod.internal", "port": 5432}
        
        # 2. Call the function
        payload = create_log_payload(level, message, details)

        # 2a. Prints the test payload
        print("--- Generated Payload ---")
        print(json.dumps(payload, indent=4))
        print("-------------------------")

        # 3. Assert (verify) the output is correct
        # Check that the inputs were placed correctly
        self.assertEqual(payload['level'], level)
        self.assertEqual(payload['message'], message)
        self.assertEqual(payload['details'], details)
        
        # Check that the function added the required metadata fields
        self.assertIn('log_id', payload)
        self.assertIsInstance(payload['log_id'], str)
        self.assertIn('timestamp', payload)
        self.assertIsInstance(payload['timestamp'], str)

        print("✅ Test passed!")

# This allows the test to be run directly
if __name__ == '__main__':
    unittest.main()