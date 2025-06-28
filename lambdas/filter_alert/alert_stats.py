# alert_stats.py
from datetime import datetime, timezone
from mad_model import MADModel
from hmm_model import HMMModel
from permutation_model import PermutationModel

class AlertDecision:
    """A simple data class to hold the outcome of the alert filter."""
    def __init__(self, alert: bool, reason: str, details: dict = None):
        self.alert = alert
        self.reason = reason
        self.details = details or {}

    def __bool__(self) -> bool:
        """Allows the object to be used in boolean contexts, like `if decision:`."""
        return self.alert

    def __repr__(self) -> str:
        return f"AlertDecision(alert={self.alert}, reason='{self.reason}')"


class AlertFilter:
    """
    A decision engine that intelligently filters alerts using only standard libraries.
    It analyzes a complete time-series of events by combining historical and
    current event timestamps.
    """
    HMM_TRUST_THRESHOLD = 20
    HMM_CONFIDENCE_THRESHOLD = 40

    def _prepare_intervals(self, historical_timestamps: list[str], current_event_timestamps: list[str]) -> tuple | None:
        """Combines and processes timestamps into intervals for analysis."""
        all_timestamps_str = historical_timestamps + current_event_timestamps
        n = len(all_timestamps_str)
        
        if n < 2:
            return None

        all_timestamps_dt = sorted([datetime.fromisoformat(ts) for ts in all_timestamps_str])
        all_intervals = [(all_timestamps_dt[i] - all_timestamps_dt[i-1]).total_seconds() / 3600.0 for i in range(1, n)]
        
        new_interval_to_test = all_intervals[-1]
        history_for_model = all_intervals[:-1]
        
        print(f" -> Total events: {n}, Total intervals: {len(all_intervals)}, Newest interval: {new_interval_to_test:.4f} hr")
        return all_intervals, new_interval_to_test, history_for_model

    def _run_hmm_analysis(self, history_for_model: list[float], new_interval_to_test: float) -> tuple[bool, str]:
        """Runs the HMM and returns its burst prediction and state name."""
        hmm = HMMModel()
        hmm_final_state = hmm.predict_final_state(history_for_model, new_interval_to_test)
        hmm_final_state_name = hmm.STATE_NAMES.get(hmm_final_state, "Unknown")
        is_hmm_burst = (hmm_final_state == HMMModel.STATE_BURST)
        print(f" -> HMM Final Prediction: '{hmm_final_state_name}'")
        return is_hmm_burst, hmm_final_state_name

    def _run_transitional_consensus_check(self, all_intervals: list[float]) -> AlertDecision:
        """Handles Zone 2 logic, requiring HMM consensus from the Permutation test."""
        print(f"\n>>> Zone: Transitional Data. Verifying HMM with PermutationModel. <<<")
        permutation_model = PermutationModel()
        is_permutation_confirmed = permutation_model.has_burst_pattern_emerged(all_intervals)

        if is_permutation_confirmed:
            return AlertDecision(True, "HMM prediction was confirmed by the Permutation Test.")
        else:
            return AlertDecision(False, "HMM burst prediction was not confirmed by the Permutation Test.")

    def should_alert(self, historical_timestamps: list[str], current_event_timestamps: list[str]) -> AlertDecision:
        """
        The main decision engine. Orchestrates the analysis based on data volume.
        """
        # Step 1: Prepare Data
        prepared_data = self._prepare_intervals(historical_timestamps, current_event_timestamps)
        if not prepared_data:
            n_events = len(historical_timestamps) + len(current_event_timestamps)
            return AlertDecision(True, f"Heuristic: Alerting on first event sequence (events={n_events}).")
        
        all_intervals, new_interval_to_test, history_for_model = prepared_data
        num_intervals = len(all_intervals)

        # Step 2: High-Priority Check with MAD Model
        mad_model = MADModel()
        if mad_model.is_burst_anomaly(new_interval_to_test, history_for_model):
            return AlertDecision(True, "High-priority MAD model detected a clear burst anomaly.")

        # Step 3: Zone-based Analysis
        # Zone 1: Low Data -> MAD was negative, so we're done.
        if num_intervals < self.HMM_TRUST_THRESHOLD:
            reason = f"Zone: Low Data (intervals={num_intervals}). MAD check was negative. No further tests."
            return AlertDecision(False, reason)
        
        # We have enough data for HMM.
        is_hmm_burst, hmm_state_name = self._run_hmm_analysis(history_for_model, new_interval_to_test)

        if not is_hmm_burst:
            reason = f"HMM did not predict a Burst state (Predicted: {hmm_state_name})."
            return AlertDecision(False, reason, details={'hmm_prediction': hmm_state_name})

        # At this point, HMM *does* predict a burst. We decide whether to trust it based on the zone.
        
        # Zone 2: Medium Data -> Require Confirmation.
        if num_intervals < self.HMM_CONFIDENCE_THRESHOLD:
            return self._run_transitional_consensus_check(all_intervals)

        # Zone 3: High Confidence Data -> Trust HMM.
        return AlertDecision(True, f"Zone: High Confidence Data (intervals={num_intervals}). Trusting HMM's prediction.")
