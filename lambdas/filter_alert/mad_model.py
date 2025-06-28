# mad_model.py
import math
import statistics

class MADModel:
    """
    Analyzes event timing anomalies using the Median Absolute Deviation (MAD) method.
    This robust statistical model is ideal for smaller datasets.
    """
    MAD_Z_SCORE_THRESHOLD = 3.5  # Standard robust threshold for anomaly detection.

    def is_burst_anomaly(self, new_interval_hr: float, historical_intervals: list[float]) -> bool:
        """
        Determines if a new event interval constitutes a burst anomaly.

        Args:
            new_interval_hr: The time in hours since the last event.
            historical_intervals: A list of previous event intervals in hours.

        Returns:
            True if the event is a burst anomaly, False otherwise.
        """
        if len(historical_intervals) < 2:
            # Fallback for very sparse data: alert on any fast event.
            return new_interval_hr < 0.1

        median = statistics.median(historical_intervals)
        # MAD is the median of the absolute differences from the median.
        mad = statistics.median([abs(interval - median) for interval in historical_intervals])

        if mad == 0:
            # If MAD is zero, all historical intervals are identical.
            # A burst is only possible if the new interval is significantly smaller.
            is_burst = new_interval_hr < median and not math.isclose(new_interval_hr, median)
            print(f"--- MAD (mad=0): {'Alerting on Burst' if is_burst else 'Filtering'}. New ({new_interval_hr:.2f}hr) vs Median ({median:.2f}hr) ---")
            return is_burst

        # A robust version of the Z-score, less sensitive to outliers.
        modified_z_score = 0.6745 * (new_interval_hr - median) / mad
        print(f"Analyzing with MAD... Median: {median:.2f}hr, MAD: {mad:.2f}hr, Mod Z-Score: {modified_z_score:.2f}")

        # For MAD, we alert only on bursts (a significantly negative z-score).
        # A positive z-score indicates a dip or silence, which we filter.
        if modified_z_score < -self.MAD_Z_SCORE_THRESHOLD:
            print(f"+++ ALERTING (MAD): Modified Z-score exceeds robust threshold. Detected Burst. +++")
            return True
        else:
            print(f"--- FILTERING (MAD): Event timing is within robust bounds or indicates a dip/silence. ---")
            return False
        