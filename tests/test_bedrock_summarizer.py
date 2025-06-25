# lambda_error_analyzer/lambdas/analyze_logs/bedrock_summarizer.py
import boto3
import json
from typing import List
from botocore.exceptions import BotoCoreError, ClientError
from pathlib import Path
import os

class BedrockSummarizer:
    """
    Uses AWS Bedrock to generate a natural-language summary of log clusters.
    """

    def __init__(self):
        """
        Initializes the Bedrock client and loads the prompt template from a file.
        """
        # Initialize the Bedrock Runtime client
        try:
            self.bedrock_runtime = boto3.client(
                service_name='bedrock-runtime',
                region_name=os.environ.get("AWS_REGION")
            )
        except (BotoCoreError, ClientError) as e:
            print(f"Error initializing Bedrock client: {e}")
            self.bedrock_runtime = None

        self.model_id = os.environ.get("BEDROCK_MODEL_ID")

        # Load the summarization prompt from an external file
        try:
            # Correctly locate the prompt file in the same directory
            prompt_path = Path(__file__).parent / "summarization_prompt.txt"
            with open(prompt_path, 'r') as f:
                self.prompt_template = f.read()
        except FileNotFoundError:
            self.prompt_template = "Error: Prompt file 'summarization_prompt.txt' not found in the same directory."

    def summarize_clusters(self, clusters: List[dict]) -> str:
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
        user_prompt = self.prompt_template.format(log_clusters_text=log_clusters_text)
        system_prompt = "You are an expert systems analyst. Your task is to provide a concise, human-readable summary of production errors."

        body = json.dumps({
            "system": [{"text": system_prompt}],
            "messages": [
                {"role": "user", "content": [{"text": user_prompt}]}
            ],
            "inferenceConfig": {
                "maxTokens": 300,
                "temperature": 0.5,
                "topP": 0.9
            }
        })

        try:
            response = self.bedrock_runtime.invoke_model(
                body=body,
                modelId=self.model_id,
                accept='application/json',
                contentType='application/json'
            )
            response_body = json.loads(response.get('body').read())
            # The response format for message-based models is consistent
            summary = response_body.get('content')[0].get('text')
            
            return summary.strip() if summary else "Failed to generate a valid summary from Bedrock."

        except (ClientError, BotoCoreError) as e:
            print(f"Bedrock API call failed: {e}. Generating basic fallback summary.")
            return self.generate_fallback_summary(clusters)
        except (KeyError, IndexError, TypeError) as e:
            print(f"Invalid Bedrock response format: {e}. Generating basic fallback summary.")
            return self.generate_fallback_summary(clusters)

    @staticmethod
    def _format_clusters_for_prompt(clusters: List[dict]) -> str:
        """
        Formats the log clusters into a string for the summarization prompt.
        """
        sorted_clusters = sorted(clusters, key=lambda c: c["count"], reverse=True)
        # Handle the possibility of 'is_recurring' not being present in the dict
        formatted_lines = []
        for c in sorted_clusters:
            recurring_tag = " (RECURRING)" if c.get("is_recurring") else ""
            formatted_lines.append(f'- Signature: "{c["signature"]}", Occurrences: {c["count"]}{recurring_tag}')
        return "\n".join(formatted_lines)
    
    @staticmethod
    def generate_fallback_summary(clusters: List[dict]) -> str:
        """Generates a simple, non-AI summary when the Bedrock API fails."""
        if not clusters:
            return "No errors detected."

        total_errors = sum(c['count'] for c in clusters)
        num_signatures = len(clusters)
        most_common_error = clusters[0]
        
        summary = (
            f"AI summary failed. Basic Analysis: Found {total_errors} errors across {num_signatures} unique signatures. "
            f"The most common error ({most_common_error['count']} times) was: '{most_common_error['signature']}'."
        )
        return summary
