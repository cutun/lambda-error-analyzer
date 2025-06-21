# lambda_error_analyzer/tests/test_bedrock_summarizer.py
import pytest
import json
from unittest.mock import MagicMock, mock_open, patch

# Adjust the import path
from lambdas.analyze_logs.bedrock_summarizer import BedrockSummarizer
from lambdas.analyze_logs.models import LogCluster

# Define the expected prompt content for mocking the file read
MOCK_PROMPT_CONTENT = "Summarize these logs:\n{log_clusters_text}"

@pytest.fixture
def sample_clusters() -> list[LogCluster]:
    """Provides a sample list of LogCluster objects for testing."""
    return [
        LogCluster(
            signature="CRITICAL: Core component 'BillingService' has failed.",
            count=2,
            log_samples=["log1", "log2"],
            representative_log="[2024-06-17T13:32:00Z] [CRITICAL] ...",
        ),
        LogCluster(
            signature="Error: Invalid credentials.",
            count=2,
            log_samples=["log3", "log4"],
            representative_log="[2024-06-17T13:31:00Z] [ERROR] ...",
        ),
    ]

@patch('lambdas.analyze_logs.bedrock_summarizer.get_settings')
@patch('builtins.open', new_callable=mock_open, read_data=MOCK_PROMPT_CONTENT)
@patch('boto3.client')
def test_summarize_clusters_with_mock_bedrock(mock_boto_client, mock_file_open, mock_get_settings, sample_clusters):
    """
    Tests the summarize_clusters method, mocking the Bedrock API call and file read.
    """
    # Arrange: Mock the Bedrock response
    mock_bedrock_runtime = MagicMock()
    mock_boto_client.return_value = mock_bedrock_runtime

    # The response body from Bedrock is a stream, so we mock its read() method
    mock_response_body = MagicMock()
    mock_response_body.read.return_value = json.dumps({
        "results": [{
            "outputText": "The system experienced 2 critical billing failures and 2 authentication errors."
        }]
    })
    
    mock_bedrock_runtime.invoke_model.return_value = {
        'body': mock_response_body
    }

    # Act
    summarizer = BedrockSummarizer()
    summary = summarizer.summarize_clusters(sample_clusters)

    # Assert
    assert summary == "The system experienced 2 critical billing failures and 2 authentication errors."
    mock_bedrock_runtime.invoke_model.assert_called_once()
    
    # Verify the prompt sent to Bedrock
    call_args = mock_bedrock_runtime.invoke_model.call_args
    request_body = json.loads(call_args.kwargs['body'])
    assert 'CRITICAL: Core component' in request_body['inputText']
    assert 'Error: Invalid credentials.' in request_body['inputText']


@patch('lambdas.analyze_logs.bedrock_summarizer.get_settings')
@patch('builtins.open', side_effect=FileNotFoundError)
def test_summarizer_init_handles_file_not_found(mock_file_open, mock_get_settings):
    """
    Tests that the summarizer handles a missing prompt file gracefully without crashing.
    """
    # ARRANGE: Mock the boto3 client to avoid real AWS calls
    with patch('boto3.client'):
        # ACT
        summarizer = BedrockSummarizer()

        # ASSERT
        assert "Error: Prompt file" in summarizer.prompt_template
        
        # Verify that calling summarize returns the error message
        summary = summarizer.summarize_clusters([MagicMock()])
        assert summary == summarizer.prompt_template
