import pytest
import yaml
import os 

from lambdas.analyze_logs.clusterer import LogClusterer
from lambdas.analyze_logs.models import LogCluster

# Define the root path to locate test files
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

@pytest.fixture(scope="module")
def log_clusterer() -> LogClusterer:
    """
    Fixture to create a LogClusterer instance, loading patterns from patterns.yml.
    """
    patterns_path = os.path.join(ROOT_DIR, 'patterns.yml')
    with open(patterns_path, 'r') as f:
        config = yaml.safe_load(f)
    return LogClusterer(patterns=config['patterns'])


@pytest.fixture(scope="module")
def raw_logs() -> list[str]:
    current_dir = os.path.dirname(__file__)  # Points to 'tests/' folder
    logs_path = os.path.join(current_dir, 'sample_logs.txt')
    with open(logs_path, 'r') as f:
        logs = f.read().split('\n\n')
    return logs


def test_clustering_groups_correctly(log_clusterer: LogClusterer, raw_logs: list[str]):
    """
    Tests that logs are grouped into the correct clusters with correct counts.
    """
    # Act
    clusters = log_clusterer.cluster_logs(raw_logs)

    # Assert
    assert len(clusters) == 2  # We expect two distinct error clusters

    # Convert to a dictionary for easier lookup
    cluster_map = {c.signature: c for c in clusters}

    # Check the "CRITICAL" cluster
    critical_sig = "CRITICAL: Core component 'BillingService' has failed."
    assert critical_sig in cluster_map
    assert cluster_map[critical_sig].count == 2
    assert len(cluster_map[critical_sig].log_samples) == 2

    # Check the "ERROR" cluster
    error_sig = "Error: Invalid credentials."
    assert error_sig in cluster_map
    assert cluster_map[error_sig].count == 2
    assert cluster_map[error_sig].representative_log.startswith("2024-06-17T13:31:00Z")


def test_unmatched_logs_are_ignored(log_clusterer: LogClusterer):
    """
    Tests that logs without a matching signature (e.g., INFO, DEBUG) are ignored.
    """
    # Arrange
    non_error_logs = [
        "2024-06-17T13:30:00Z [INFO] Service started successfully.",
        "2024-06-17T13:33:00Z [DEBUG] A-OK."
    ]

    # Act
    clusters = log_clusterer.cluster_logs(non_error_logs)

    # Assert
    assert len(clusters) == 0