# hmm_model.py
import math
import statistics
from collections import defaultdict

class HMMModel:
    """
    A self-learning 3-state (Normal, Burst, Silent) Hidden Markov Model (HMM)
    to analyze the timing of sequential events.
    """
    # Configuration
    _MAX_ITERATIONS = 10
    _CONVERGENCE_TOLERANCE = 1e-4
    _VITERBI_BASELINE_WINDOW = 20

    # State Representation
    STATE_NORMAL = 0
    STATE_BURST = 1
    STATE_SILENT = 2
    STATES = [STATE_NORMAL, STATE_BURST, STATE_SILENT]
    STATE_NAMES = {STATE_NORMAL: "Normal", STATE_BURST: "Burst", STATE_SILENT: "Silent"}

    class _ViterbiState:
        """Helper class to hold state probabilities for the Viterbi algorithm."""
        def __init__(self):
            log_prob = math.log(1.0 / 3.0)
            self.log_probs = {
                HMMModel.STATE_NORMAL: log_prob,
                HMMModel.STATE_BURST: log_prob,
                HMMModel.STATE_SILENT: log_prob,
            }

    def predict_final_state(self, intervals_hr: list[float], new_interval_hr: float) -> int:
        """
        Learns from historical intervals and predicts the state of a new interval.

        Args:
            intervals_hr: A list of historical event intervals in hours.
            new_interval_hr: The latest event interval to classify.

        Returns:
            The integer representing the most likely final state (e.g., HMMModel.STATE_BURST).
        """
        print("\n>>> Analyzing with Self-Learning 3-State Hidden Markov Model <<<")
        model_params = self._learn_parameters(intervals_hr)
        print(f"Learned Model Parameters: {model_params}")

        # Establish a baseline state using the last 5 known intervals.
        state = self._ViterbiState()
        recent_intervals = intervals_hr[-self._VITERBI_BASELINE_WINDOW:]
        print(f"Establishing baseline state from last {len(recent_intervals)} intervals...")
        for interval in recent_intervals:
            state, _ = self._viterbi_update(interval, state, model_params)

        # Finally, analyze the new event interval.
        print(f"Analyzing new interval of {new_interval_hr:.2f} hours...")
        _, final_state = self._viterbi_update(new_interval_hr, state, model_params)
        return final_state

    def _get_poisson_log_prob(self, observed_interval_hr: float, mean_interval_hr: float) -> float:
        lambda_rate = 1.0 / (mean_interval_hr or 1e-9)
        return math.log(lambda_rate or 1e-9) - lambda_rate * observed_interval_hr

    def _initialize_parameters(self, intervals: list[float]) -> tuple[list, list]:
        """Creates an initial guess for the HMM parameters."""
        transitions = [
            [0.90, 0.08, 0.02],  # Normal -> (Normal, Burst, Silent)
            [0.20, 0.79, 0.01],  # Burst  -> (Normal, Burst, Silent)
            [0.30, 0.01, 0.69]   # Silent -> (Normal, Burst, Silent)
        ]
        mean_normal = statistics.mean(intervals) if intervals else 24.0
        lambdas = [
            1.0 / (mean_normal or 1e-9),                     # Normal
            1.0 / ((mean_normal * 0.05) or 1e-9),             # Burst
            1.0 / ((mean_normal * 10.0) or 1e-9)             # Silent
        ]
        return transitions, lambdas

    def _precompute_observation_log_probs(self, intervals: list[float], lambdas: list) -> list[list[float]]:
        num_obs, num_states = len(intervals), len(lambdas)
        obs_log_probs = [[0.0] * num_states for _ in range(num_obs)]
        for t in range(num_obs):
            for s in range(num_states):
                mean_interval = 1.0 / (lambdas[s] or 1e-9)
                obs_log_probs[t][s] = self._get_poisson_log_prob(intervals[t], mean_interval)
        return obs_log_probs

    def _baum_welch_e_step(self, intervals: list[float], transitions: list, obs_log_probs: list[list[float]]) -> tuple[list, list]:
        num_states, num_obs = len(self.STATES), len(intervals)
        alpha = [[0.0] * num_states for _ in range(num_obs)]
        alpha[0] = [math.log(1.0 / num_states) + p for p in obs_log_probs[0]]
        for t in range(1, num_obs):
            for j in range(num_states):
                log_sum = -math.inf
                for i in range(num_states):
                    term = alpha[t-1][i] + math.log(transitions[i][j] or 1e-9)
                    log_sum = max(log_sum, term)
                alpha[t][j] = obs_log_probs[t][j] + log_sum

        beta = [[0.0] * num_states for _ in range(num_obs)]
        for t in range(num_obs - 2, -1, -1):
            for i in range(num_states):
                log_sum = -math.inf
                for j in range(num_states):
                    term = beta[t+1][j] + math.log(transitions[i][j] or 1e-9) + obs_log_probs[t+1][j]
                    log_sum = max(log_sum, term)
                beta[t][i] = log_sum
        return alpha, beta

    def _baum_welch_m_step(self, intervals: list[float], transitions: list, alpha: list, beta: list, obs_log_probs: list[list[float]]) -> tuple[list, list]:
        num_states, num_obs = len(self.STATES), len(intervals)
        gamma = [[0.0] * num_states for _ in range(num_obs)]
        xi = defaultdict(lambda: [[0.0] * num_states for _ in range(num_states)])
        for t in range(num_obs):
            log_denominator = max(alpha[t][i] + beta[t][i] for i in range(num_states))
            for i in range(num_states):
                gamma[t][i] = math.exp(alpha[t][i] + beta[t][i] - log_denominator)
            if t < num_obs - 1:
                for i in range(num_states):
                    for j in range(num_states):
                        numerator = alpha[t][i] + math.log(transitions[i][j] or 1e-9) + beta[t+1][j] + obs_log_probs[t+1][j]
                        xi[t][i][j] = math.exp(numerator - log_denominator)
        
        new_transitions = [[0.0] * num_states for _ in range(num_states)]
        for i in range(num_states):
            gamma_sum = sum(gamma[t][i] for t in range(num_obs - 1))
            for j in range(num_states):
                new_transitions[i][j] = sum(xi[t][i][j] for t in range(num_obs - 1)) / (gamma_sum or 1)
        
        new_lambdas = [0.0] * num_states
        for i in range(num_states):
            gamma_sum = sum(gamma[t][i] for t in range(num_obs))
            weighted_interval_sum = sum(gamma[t][i] * intervals[t] for t in range(num_obs))
            new_lambdas[i] = gamma_sum / (weighted_interval_sum or 1e-9)
        return new_transitions, new_lambdas

    def _learn_parameters(self, intervals: list[float]) -> dict:
        """Orchestrates the Baum-Welch algorithm."""
        transitions, lambdas = self._initialize_parameters(intervals)
        num_states = len(self.STATES)
        for iteration in range(self._MAX_ITERATIONS):
            obs_log_probs = self._precompute_observation_log_probs(intervals, lambdas)
            alpha, beta = self._baum_welch_e_step(intervals, transitions, obs_log_probs)
            new_transitions, new_lambdas = self._baum_welch_m_step(intervals, transitions, alpha, beta, obs_log_probs)
            change = sum(abs(new_transitions[i][j] - transitions[i][j]) for i in range(num_states) for j in range(num_states))
            change += sum(abs(new_lambdas[i] - lambdas[i]) for i in range(num_states))
            transitions, lambdas = new_transitions, new_lambdas
            if change < self._CONVERGENCE_TOLERANCE:
                print(f"Baum-Welch converged after {iteration + 1} iterations.")
                break
        else:
             print("Baum-Welch reached max iterations.")
        return {
            'means': {self.STATE_NAMES[s]: 1.0 / lambdas[s] for s in self.STATES},
            'transitions': transitions
        }

    def _viterbi_update(self, observed_interval_hr: float, prev_state: _ViterbiState, model_params: dict) -> tuple[_ViterbiState, int]:
        """Performs one step of the Viterbi algorithm."""
        obs_log_probs = {
            s: self._get_poisson_log_prob(observed_interval_hr, model_params['means'][self.STATE_NAMES[s]])
            for s in self.STATES
        }
        new_state = self._ViterbiState()
        t = model_params['transitions']
        for dest_s in self.STATES:
            max_path_prob = -math.inf
            for src_s in self.STATES:
                path_prob = prev_state.log_probs[src_s] + math.log(t[src_s][dest_s] or 1e-9)
                if path_prob > max_path_prob:
                    max_path_prob = path_prob
            new_state.log_probs[dest_s] = max_path_prob + obs_log_probs[dest_s]
        most_likely_state = max(new_state.log_probs, key=new_state.log_probs.get)
        return new_state, most_likely_state
        