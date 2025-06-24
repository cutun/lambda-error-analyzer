# lambda_error_analyzer/lambdas/analyze_logs/detector.py
import boto3
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone

from .models import LogCluster, get_settings

class PatternDetector:
    """
    Detects recurring error patterns and calculates an anomaly score by
    checking against historical state stored in a DynamoDB table.
    """
    def __init__(self):
        """Initializes the detector with settings and a DynamoDB client."""
        self.settings = get_settings()
        self.dynamodb = boto3.resource('dynamodb', region_name=self.settings.aws_region)
        self.state_table = self.dynamodb.Table(self.settings.error_state_table_name)

    def analyze_patterns(self, clusters: List[LogCluster]):
        """
        Processes a list of LogCluster objects, checks for recurrence,
        calculates anomaly scores, and updates their state in DynamoDB.

        This method modifies the LogCluster objects in-place.
        """
        print("Analyzing error patterns for recurrence and anomalies...")
        for cluster in clusters:
            try:
                # 1. Get the current state for this error signature
                response = self.state_table.get_item(Key={'signature': cluster.signature})
                current_state = response.get('Item')
                
                # 2. Analyze, flag for recurrence, and calculate anomaly score
                self._analyze_and_score_cluster(cluster, current_state)

                # 3. Update the state in DynamoDB for the next run
                self._update_error_state(cluster, current_state)

            except Exception as e:
                print(f"Could not process patterns for signature '{cluster.signature}': {e}")
                # Continue to the next cluster even if one fails

    def _analyze_and_score_cluster(self, cluster: LogCluster, state: Optional[Dict[str, Any]]):
        """Analyzes a cluster against its historical state, flags it, and scores it."""
        if not state:
            # First time seeing this error. Can't be recurring or anomalous yet.
            cluster.is_recurring = False
            cluster.anomaly_score = 1.0 # A score of 1.0 is neutral
            return

        # --- Recurrence Logic ---
        last_seen_dt = datetime.fromisoformat(state['last_seen_timestamp'])
        time_window = timedelta(seconds=self.settings.recurrence_time_window_seconds)
        if (datetime.now(timezone.utc) - last_seen_dt) < time_window:
            # The 'total_count' from the state includes all historical occurrences.
            # We add the new batch's count to see if it crosses the threshold now.
            total_count_with_current = int(state['total_count']) + cluster.count
            if total_count_with_current >= self.settings.recurrence_count_threshold:
                print(f"FLAGGED RECURRING: '{cluster.signature}' (total count: {total_count_with_current})")
                cluster.is_recurring = True

        # --- Anomaly Score Logic ("baseline vs current") ---
        first_seen_dt = datetime.fromisoformat(state['first_seen_timestamp'])
        total_duration_hours = (datetime.now(timezone.utc) - first_seen_dt).total_seconds() / 3600.0

        # Avoid division by zero if the event is very new
        if total_duration_hours < 1.0:
            total_duration_hours = 1.0
        
        baseline_rate_per_hour = int(state['total_count']) / total_duration_hours
        
        # If the historical rate is very low, use a default to avoid huge scores
        if baseline_rate_per_hour < self.settings.default_baseline_rate_per_hour:
             baseline_rate_per_hour = self.settings.default_baseline_rate_per_hour

        # The "current rate" is simply the count in this batch (assuming batches are roughly hourly)
        current_rate_per_hour = float(cluster.count)
        
        # Calculate the score and round it for cleanliness
        cluster.anomaly_score = round(current_rate_per_hour / baseline_rate_per_hour, 2)
        print(f"ANOMALY SCORE for '{cluster.signature}': {cluster.anomaly_score} (current: {current_rate_per_hour:.2f}/hr, baseline: {baseline_rate_per_hour:.2f}/hr)")


    def _update_error_state(self, cluster: LogCluster, state: Optional[Dict[str, Any]]):
        """Updates the count and timestamps for an error signature in DynamoDB."""
        now_iso = datetime.now(timezone.utc).isoformat()
        
        if state:
            # Update existing state by adding the current count to the total
            new_total_count = int(state['total_count']) + cluster.count
            self.state_table.update_item(
                Key={'signature': cluster.signature},
                UpdateExpression="SET #total_count = :tc, #last_seen = :ls",
                ExpressionAttributeNames={
                    '#total_count': 'total_count',
                    '#last_seen': 'last_seen_timestamp'
                },
                ExpressionAttributeValues={
                    ':tc': new_total_count,
                    ':ls': now_iso
                }
            )
        else:
            # Create new state for a signature seen for the first time
            self.state_table.put_item(
                Item={
                    'signature': cluster.signature,
                    'total_count': cluster.count,
                    'first_seen_timestamp': now_iso,
                    'last_seen_timestamp': now_iso
                }
            )
