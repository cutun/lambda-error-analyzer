import math
import statistics
from datetime import datetime, timezone
from collections import defaultdict

class AlertFilter:
    """
    A class containing static methods to determine if an alert should be triggered
    based on the historical timing of events.
    
    This class uses a self-learning Hidden Markov Model (HMM). For rich data,
    it applies the Baum-Welch algorithm to learn model parameters, then uses the
    Viterbi algorithm to detect state changes.
    """

    class _ViterbiState:
        """A simple helper class to hold state for the Viterbi algorithm."""
        def __init__(self):
            self.log_prob_state0 = math.log(0.5) # State 0: Normal
            self.log_prob_state1 = math.log(0.5) # State 1: Burst

    @staticmethod
    def _learn_hmm_parameters(intervals: list[float], max_iterations=10, tolerance=1e-4) -> dict:
        """
        Implements the Baum-Welch algorithm (Expectation-Maximization) to learn
        the HMM parameters (transition and emission probabilities) from the data.
        """
        print("--- Learning HMM parameters with Baum-Welch algorithm... ---")
        num_states = 2
        num_obs = len(intervals)

        # --- Initial Guess ---
        transitions = [[0.95, 0.05], [0.20, 0.80]]
        mean_normal = statistics.mean(intervals) if intervals else 24.0
        mean_burst = mean_normal * 0.05
        lambdas = [1.0 / (mean_normal or 0.001), 1.0 / (mean_burst or 0.001)]

        for iteration in range(max_iterations):
            # --- E-Step: Forward-Backward Algorithm ---
            alpha = [[0.0] * num_states for _ in range(num_obs)]
            obs_prob = [lamb * math.exp(-lamb * intervals[0]) for lamb in lambdas]
            alpha[0] = [math.log(0.5) + math.log(p or 1e-9) for p in obs_prob]

            for t in range(1, num_obs):
                obs_prob = [lamb * math.exp(-lamb * intervals[t]) for lamb in lambdas]
                for j in range(num_states):
                    log_sum = -math.inf
                    for i in range(num_states):
                        term = alpha[t-1][i] + math.log(transitions[i][j] or 1e-9)
                        if term > log_sum: log_sum = term
                    alpha[t][j] = math.log(obs_prob[j] or 1e-9) + log_sum

            beta = [[0.0] * num_states for _ in range(num_obs)]
            for t in range(num_obs - 2, -1, -1):
                obs_prob_next = [lamb * math.exp(-lamb * intervals[t+1]) for lamb in lambdas]
                for i in range(num_states):
                    log_sum = -math.inf
                    for j in range(num_states):
                        term = beta[t+1][j] + math.log(transitions[i][j] or 1e-9) + math.log(obs_prob_next[j] or 1e-9)
                        if term > log_sum: log_sum = term
                    beta[t][i] = log_sum

            gamma = [[0.0] * num_states for _ in range(num_obs)]
            xi = defaultdict(lambda: [[0.0] * num_states for _ in range(num_states)])
            
            for t in range(num_obs):
                log_denominator = -math.inf
                for i in range(num_states):
                    term = alpha[t][i] + beta[t][i]
                    if term > log_denominator: log_denominator = term
                for i in range(num_states):
                    gamma[t][i] = math.exp(alpha[t][i] + beta[t][i] - log_denominator)
                if t < num_obs - 1:
                    obs_prob_next = [lamb * math.exp(-lamb * intervals[t+1]) for lamb in lambdas]
                    for i in range(num_states):
                        for j in range(num_states):
                           numerator = alpha[t][i] + math.log(transitions[i][j] or 1e-9) + beta[t+1][j] + math.log(obs_prob_next[j] or 1e-9)
                           xi[t][i][j] = math.exp(numerator - log_denominator)

            # --- M-Step: Re-estimate parameters ---
            new_transitions = [[0.0] * num_states for _ in range(num_states)]
            for i in range(num_states):
                gamma_sum = sum(gamma[t][i] for t in range(num_obs - 1))
                for j in range(num_states):
                    xi_sum = sum(xi[t][i][j] for t in range(num_obs - 1))
                    new_transitions[i][j] = xi_sum / (gamma_sum or 1)
            
            new_lambdas = [0.0] * num_states
            for i in range(num_states):
                gamma_sum = sum(gamma[t][i] for t in range(num_obs))
                weighted_interval_sum = sum(gamma[t][i] * intervals[t] for t in range(num_obs))
                new_lambdas[i] = gamma_sum / (weighted_interval_sum or 1e-9)

            change = sum(abs(new_transitions[i][j] - transitions[i][j]) for i in range(num_states) for j in range(num_states))
            change += sum(abs(new_lambdas[i] - lambdas[i]) for i in range(num_states))
            transitions, lambdas = new_transitions, new_lambdas
            if change < tolerance:
                print(f"Baum-Welch converged after {iteration + 1} iterations.")
                break
        else:
             print("Baum-Welch reached max iterations.")

        return {'mean_normal': 1.0 / lambdas[0], 'mean_burst': 1.0 / lambdas[1],
                'transitions': {'norm_norm': transitions[0][0], 'norm_burst': transitions[0][1],
                                'burst_burst': transitions[1][1], 'burst_norm': transitions[1][0]}}

    @staticmethod
    def _viterbi_update(observed_interval_hr: float, prev_state: _ViterbiState, model_params: dict) -> tuple[_ViterbiState, bool]:
        """Performs one step of the Viterbi algorithm to find the most likely current state."""
        lambda0 = 1.0 / model_params['mean_normal']
        lambda1 = 1.0 / model_params['mean_burst']
        log_emission_prob_state0 = math.log(lambda0 or 1e-9) - lambda0 * observed_interval_hr
        log_emission_prob_state1 = math.log(lambda1 or 1e-9) - lambda1 * observed_interval_hr
        t = model_params['transitions']
        path_to_0 = max(prev_state.log_prob_state0 + math.log(t['norm_norm'] or 1e-9), prev_state.log_prob_state1 + math.log(t['burst_norm'] or 1e-9))
        path_to_1 = max(prev_state.log_prob_state0 + math.log(t['norm_burst'] or 1e-9), prev_state.log_prob_state1 + math.log(t['burst_burst'] or 1e-9))
        new_state = AlertFilter._ViterbiState()
        new_state.log_prob_state0 = path_to_0 + log_emission_prob_state0
        new_state.log_prob_state1 = path_to_1 + log_emission_prob_state1
        is_burst_state = new_state.log_prob_state1 > new_state.log_prob_state0
        return new_state, is_burst_state

    @staticmethod
    def _should_alert_by_mad_interval(new_interval_hr: float, historical_intervals: list[float], threshold: float = 3.5) -> bool:
        """A robust check for interval anomalies using Median Absolute Deviation."""
        n = len(historical_intervals)
        if n < 2: return new_interval_hr < 0.1 # Not enough data for MAD, fallback to a simple burst check
        
        median = statistics.median(historical_intervals)
        abs_diff_from_median = [abs(interval - median) for interval in historical_intervals]
        mad = statistics.median(abs_diff_from_median)

        if mad == 0:
            is_different = not math.isclose(new_interval_hr, median)
            print(f"--- MAD Interval (mad=0): {'Alerting' if is_different else 'Filtering'}. New interval ({new_interval_hr:.2f}hr) {'!=' if is_different else '=='} stable median ({median:.2f}hr) ---")
            return is_different

        modified_z_score = 0.6745 * (new_interval_hr - median) / mad
        print(f"Analyzing with MAD Interval... Median: {median:.2f}hr, MAD: {mad:.2f}hr, Mod Z-Score: {modified_z_score:.2f}")

        if abs(modified_z_score) > threshold:
            alert_type = "Burst" if modified_z_score < 0 else "Dip/Silence"
            print(f"+++ ALERTING (MAD): Modified Z-score ({modified_z_score:.2f}) exceeds robust threshold ({threshold}). Detected {alert_type}. +++")
            return True
        else:
            print(f"--- FILTERING (MAD): Event timing is within robust bounds. ---")
            return False

    @staticmethod
    def should_alert(historical_timestamps: list[str]) -> bool:
        """The main decision engine. Uses HMM and learns parameters via Baum-Welch."""
        n = len(historical_timestamps)
        TRUST_THRESHOLD = 20 # Need at least 20 data points to reliably learn parameters

        # --- UPDATED: Heuristic block with MAD for better robustness ---
        if n < TRUST_THRESHOLD:
            print(f"\n>>> Analyzing with Heuristic (n={n}) <<<")
            if n == 0:
                print("--- Heuristic (n=0): Alerting on first ever event. ---")
                return True
            
            # For all other sparse cases, we can use the robust MAD method.
            timestamps = [datetime.fromisoformat(ts) for ts in sorted(historical_timestamps)]
            last_event_ts = timestamps[-1]
            new_interval_hr = (datetime.now(timezone.utc) - last_event_ts).total_seconds() / 3600.0
            
            historical_intervals = [(timestamps[i] - timestamps[i-1]).total_seconds() / 3600 for i in range(1, n)]
            return AlertFilter._should_alert_by_mad_interval(new_interval_hr, historical_intervals)

        # --- Self-Learning HMM Analysis for Rich Data (n >= 20) ---
        print("\n>>> Analyzing with Self-Learning Hidden Markov Model <<<")
        timestamps = [datetime.fromisoformat(ts) for ts in sorted(historical_timestamps)]
        intervals_hr = [(timestamps[i] - timestamps[i-1]).total_seconds() / 3600 for i in range(1, n)]

        model_params = AlertFilter._learn_hmm_parameters(intervals_hr)
        print(f"Learned Model Parameters: {model_params}")

        state = AlertFilter._ViterbiState()
        recent_intervals = intervals_hr[-5:] # Use last 5 intervals for current state
        print(f"Establishing baseline state from last {len(recent_intervals)} intervals...")
        for interval in recent_intervals:
            state, _ = AlertFilter._viterbi_update(interval, state, model_params)

        last_event_ts = timestamps[-1]
        new_interval_hr = (datetime.now(timezone.utc) - last_event_ts).total_seconds() / 3600.0
        print(f"Analyzing new interval of {new_interval_hr:.2f} hours...")
        _, should_alert = AlertFilter._viterbi_update(new_interval_hr, state, model_params)

        if should_alert:
            print(f"+++ ALERTING: HMM detected a state transition to 'Burst'. +++")
        else:
            print(f"--- FILTERING: HMM indicates system remains in 'Normal' state. ---")
            
        return should_alert
