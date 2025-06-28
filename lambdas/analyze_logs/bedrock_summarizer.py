# lambda_error_analyzer/lambdas/analyze_logs/bedrock_summarizer.py
import json
import os
from pathlib import Path
from typing import List, Dict, Any, Optional

import boto3
from botocore.exceptions import BotoCoreError, ClientError

# Resource & Client Initialization
AWS_REGION = None
BEDROCK_MODEL_ID = None
BEDROCK_RUNTIME = None
try:
    AWS_REGION = os.environ['AWS_REGION']
    BEDROCK_MODEL_ID = os.environ['BEDROCK_MODEL_ID']
    BEDROCK_RUNTIME = boto3.client(
        service_name="bedrock-runtime",
        region_name=AWS_REGION,
    )
except KeyError as e:
    print(f"FATAL: Missing required environment variable: {e}")
    raise e
except (BotoCoreError, ClientError) as e:
    print(f"Error initializing Bedrock client: {e}")
    raise e


class BedrockSummarizer:
    """
    Uses AWS Bedrock to generate a natural-language summary of log clusters.

    This class is model-agnostic and can build the correct request format for
    different model families (e.g., Amazon Nova vs. Anthropic Claude).
    """
    def __init__(self):
        """Initializes the prompt template."""
        
        self.bedrock_runtime = BEDROCK_RUNTIME
        self.bedrock_model_id = BEDROCK_MODEL_ID
        # Load the prompts
        try:
            prompt_path = Path(__file__).parent / "summarization_prompt.txt" # make sure change this to where your prompt locate to
            self.prompt_template = prompt_path.read_text()
        except FileNotFoundError:
            self.prompt_template = (
                "Error: Prompt file 'summarization_prompt.txt' not found."
            )

    def summarize_clusters(self, clusters: List[Dict[str, Any]]) -> str:
        """
        Generates an English summary for the given log clusters.

        Falls back to a deterministic summary if the Bedrock API is unavailable
        or if the response cannot be parsed.
        """
        if not self.bedrock_runtime:
            return "Bedrock client is not initialized. Cannot generate summary."
        if not clusters:
            return "No log clusters were provided for summarization."
        if "Error:" in self.prompt_template:
            return self.prompt_template

        # compose the prompt
        log_clusters_text = self._format_clusters_for_prompt(clusters)
        user_prompt = self.prompt_template.format(log_clusters_text=log_clusters_text)
        
        # build and then send
        request_body = self._build_request_body(user_prompt)
        
        try:
            response = self.bedrock_runtime.invoke_model(
                modelId=self.bedrock_model_id,
                body=json.dumps(request_body),
                accept="application/json",
                contentType="application/json",
            )
            response_body = json.loads(response["body"].read())
            
            # we extract the LLM summary and return it
            summary_text = self._extract_text_from_response(response_body)
            if not summary_text:
                raise ValueError(f"Could not find summary text in Bedrock response: {response_body}")
            
            return summary_text.strip()

        except (BotoCoreError, ClientError, ValueError, KeyError, IndexError, TypeError) as e:
            print(f"Bedrock API problem: {e}. Falling back to basic summary.")
            return self.generate_fallback_summary(clusters)

    def _build_request_body(self, user_prompt: str) -> Dict[str, Any]:
        """
        Returns the exact JSON payload required by the current model family.
        This allows for easy swapping of model IDs in the environment variables.
        """
        system_prompt = (
            "You are an expert systems analyst. Provide a concise, actionable "
            "summary of these production error clusters."
        )

        if self.bedrock_model_id.startswith("amazon.nova"):
            # Schema for Amazon Nova models
            return {
                "system": [{"text": system_prompt}],
                "messages": [{"role": "user", "content": [{"text": user_prompt}]}],
                "inferenceConfig": {
                    "maxTokens": 300,
                    "temperature": 0.5,
                    "topP": 0.9,
                },
            }
        else:
            # Default to the schema for Anthropic Claude models
            return {
                "system": system_prompt,
                "messages": [{"role": "user", "content": [{"type": "text", "text": user_prompt}]}],
                "max_tokens": 300,
                "temperature": 0.5,
                "top_p": 0.9,
                "anthropic_version": "bedrock-2023-05-31",
            }
        
    @staticmethod
    def _extract_text_from_response(body: Dict[str, Any]) -> Optional[str]:
        """
        Safely extracts the assistant's reply text from various possible
        Bedrock response structures.
        """
        # Amazon Nova (InvokeModel)
        if "output" in body:
            blocks = (
                body.get("output", {})
                .get("message", {})
                .get("content", [])
            )
            for block in blocks:
                if isinstance(block, dict) and block.get("text"):
                    return block["text"]

        # Claude-family (Anthropic)
        if isinstance(body.get("content"), list):
            first = body["content"][0]
            if isinstance(first, dict) and first.get("text"):
                return first["text"]
            
        # Fallback for older Amazon Titan models
        results_list = body.get("results")
        if isinstance(results_list, list) and results_list:
            first_item = results_list[0]
            if isinstance(first_item, dict):
                return first_item.get("outputText")
        return None

    @staticmethod
    def _format_clusters_for_prompt(clusters: List[Dict[str, Any]]) -> str:
        """Formats clusters as bullet points, with the most frequent first."""
        sorted_clusters = sorted(clusters, key=lambda c: c["count"], reverse=True)
        lines = [
            f'- Signature: "{c["signature"]}", Occurrences: {c["count"]}'
            for c in sorted_clusters
        ]
        return "\n".join(lines)

    @staticmethod
    def generate_fallback_summary(clusters: List[Dict[str, Any]]) -> str:
        """
        Deterministic summary used when the Bedrock API cannot be reached or parsed.
        """
        if not clusters:
            return "No errors detected."

        total_errors = sum(c["count"] for c in clusters)
        num_signatures = len(clusters)
        most_common = clusters[0]

        return (
            "AI summary failed. Basic Analysis: "
            f"Found {total_errors} errors across {num_signatures} unique signatures. "
            f"The most common error ({most_common['count']} times) was: "
            f"'{most_common['signature']}'."
        )
