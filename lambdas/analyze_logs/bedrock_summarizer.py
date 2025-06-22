# lambda_error_analyzer/lambdas/analyze_logs/bedrock_summarizer.py
import boto3
import json
from typing import List
from botocore.exceptions import BotoCoreError, ClientError
from pathlib import Path

# Assuming models.py and its get_settings function are in the same directory
from .models import LogCluster, get_settings

class BedrockSummarizer:
    """
    Uses AWS Bedrock to generate a natural-language summary of log clusters.
    """

    def __init__(self):
        """
        Initializes the Bedrock client and loads the prompt template from a file.
        """
        settings = get_settings()
        # Initialize the Bedrock Runtime client
        try:
            self.bedrock_runtime = boto3.client(
                service_name='bedrock-runtime',
                region_name=settings.aws_region
            )
        except (BotoCoreError, ClientError) as e:
            print(f"Error initializing Bedrock client: {e}")
            self.bedrock_runtime = None

        self.model_id = settings.bedrock_model_id

        # Load the summarization prompt from an external file
        try:
            project_root = Path(__file__).resolve().parents[2]
            prompt_path = project_root / "prompts" / "summarization_prompt.txt"
            with open(prompt_path, 'r') as f:
                self.prompt_template = f.read()
        except FileNotFoundError:
            self.prompt_template = "Error: Prompt file 'prompts/summarization_prompt.txt' not found."

    def summarize_clusters(self, clusters: List[LogCluster]) -> str:
        """
        Generates a summary for a list of LogCluster objects using Bedrock.
        """
        if not self.bedrock_runtime:
            return "Bedrock client is not initialized. Cannot generate summary."
        if not clusters:
            return "No log clusters were provided for summarization."
        if "Error:" in self.prompt_template:
            return self.prompt_template

        log_clusters_text = self._format_clusters_for_prompt(clusters)
        prompt = self.prompt_template.format(log_clusters_text=log_clusters_text)

        # --- FINAL FIX: Corrected the body to match the specific model's requirements ---
        # The API rejected 'max_tokens' as an extraneous key. We remove it and let the model
        # use its default output length, which is usually sufficient for a summary.
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        })

        try:
            response = self.bedrock_runtime.invoke_model(
                body=body,
                modelId=self.model_id,
                accept='application/json',
                contentType='application/json'
            )
            response_body = json.loads(response.get('body').read())
            summary = response_body.get('content')[0].get('text')
            
            return summary.strip() if summary else "Failed to generate a valid summary from Bedrock."

        except (ClientError, BotoCoreError) as e:
            return f"Error communicating with Bedrock API: {e}"
        except (KeyError, IndexError, TypeError) as e:
            response_body_str = "unavailable"
            try:
                response_body_str = json.dumps(response_body)
            except NameError:
                pass
            return f"Received an invalid or unexpected response format from Bedrock API: {e}. Response: {response_body_str}"

    @staticmethod
    def _format_clusters_for_prompt(clusters: List[LogCluster]) -> str:
        """
        Formats the log clusters into a string for the summarization prompt.
        """
        sorted_clusters = sorted(clusters, key=lambda c: c.count, reverse=True)
        formatted_lines = [f'- Signature: "{c.signature}", Occurrences: {c.count}' for c in sorted_clusters]
        return "\n".join(formatted_lines)
