# permutation_model.py
import random
import statistics

class PermutationModel:
    """
    Uses a permutation test to detect a statistically significant change
    in the mean of event intervals. This is a non-parametric test that
    does not require external libraries like scipy.
    """
    ALPHA = 0.05  # Significance level
    MIN_SAMPLE_SIZE = 5
    N_PERMUTATIONS = 1000  # Number of shuffles to perform

    def has_burst_pattern_emerged(self, historical_intervals: list[float]) -> bool:
        """
        Tests if the mean of recent intervals is significantly lower (a burst)
        than the mean of older intervals using permutation testing.

        Args:
            historical_intervals: A list of all historical event intervals.

        Returns:
            True if a statistically significant burst pattern is detected.
        """
        n = len(historical_intervals)
        recent_window_size = max(self.MIN_SAMPLE_SIZE, int(n * 0.25))

        if n < recent_window_size + self.MIN_SAMPLE_SIZE:
            print(" -> PermutationModel: Insufficient data to perform a reliable test.")
            return False

        recent_sample = historical_intervals[-recent_window_size:]
        historical_sample = historical_intervals[:-recent_window_size]

        print(f" -> PermutationModel: Comparing recent {len(recent_sample)} events to historical {len(historical_sample)} events.")

        try:
            mean_recent = statistics.mean(recent_sample)
            mean_hist = statistics.mean(historical_sample)
        except statistics.StatisticsError:
            print(" -> PermutationModel: Could not calculate mean.")
            return False

        # The observed difference we want to test
        observed_difference = mean_recent - mean_hist

        # We are testing for a burst, so the difference should be negative.
        if observed_difference >= 0:
            print(" -> PermutationModel: Recent mean is not lower than historical mean. No burst detected.")
            return False

        # Pool all the data together for shuffling
        pooled_data = historical_sample + recent_sample
        count_extreme = 0

        for _ in range(self.N_PERMUTATIONS):
            random.shuffle(pooled_data)

            # Create new pseudo-samples from the shuffled data
            pseudo_recent = pooled_data[:len(recent_sample)]
            pseudo_hist = pooled_data[len(recent_sample):]

            try:
                pseudo_diff = statistics.mean(pseudo_recent) - statistics.mean(pseudo_hist)
            except statistics.StatisticsError:
                continue

            # Count how many simulated differences are as extreme as or more extreme
            if pseudo_diff <= observed_difference:
                count_extreme += 1

        p_value = count_extreme / self.N_PERMUTATIONS

        print(f" -> PermutationModel: Observed Mean Difference={observed_difference:.2f}, p-value={p_value:.4f}")

        if p_value < self.ALPHA:
            print(f" -> PermutationModel: ✅ Detected a significant shift to a lower mean interval (p < {self.ALPHA}).")
            return True
        else:
            print(f" -> PermutationModel: ❌ No significant evidence of a new burst pattern.")
            return False
