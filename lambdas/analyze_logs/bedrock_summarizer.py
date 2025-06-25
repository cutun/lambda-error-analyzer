# lambda_error_analyzer/lambdas/analyze_logs/bedrock_summarizer.py
import json
from pathlib import Path
from typing import List

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from models import LogCluster, get_settings


class BedrockSummarizer:

    def __init__(self):
        settings = get_settings()

        try:
            self.bedrock_runtime = boto3.client(
                service_name="bedrock-runtime",
                region_name=settings.aws_region,
            )
        except (BotoCoreError, ClientError) as e:
            print(f"Error initializing Bedrock client: {e}")
            self.bedrock_runtime = None

        self.model_id = settings.bedrock_model_id

        try:
            project_root = Path(__file__).resolve().parents[2]
            prompt_path = "summarization_prompt.txt"
            with open(prompt_path, "r") as f:
                self.prompt_template = f.read()
        except FileNotFoundError:
            self.prompt_template = (
                "Error: Prompt file 'prompts/summarization_prompt.txt' not found."
            )

    #  Public API
    def summarize_clusters(self, clusters: List[dict]) -> str:
        """
        Generates an English summary of the supplied `LogCluster` objects using
        the configured Bedrock model.  Falls back to a deterministic summary if
        the API is unavailable or the response cannot be parsed.
        """
        # Basic guards
        if not self.bedrock_runtime:
            return "Bedrock client is not initialized. Cannot generate summary."
        if not clusters:
            return "No log clusters were provided for summarization."
        if "Error:" in self.prompt_template:
            return self.prompt_template

        # Compose the user prompt
        log_clusters_text = self._format_clusters_for_prompt(clusters)
        user_prompt = self.prompt_template.format(log_clusters_text=log_clusters_text)
        system_prompt = (
            "You are an expert systems analyst.  Provide a concise, actionable "
            "summary of these production error clusters."
        )

        # Build & send request
        body_json = json.dumps(
            self._build_request_body(system_prompt, user_prompt),
            separators=(",", ":"),
        )

        try:
            response = self.bedrock_runtime.invoke_model(
                modelId=self.model_id,
                body=body_json,
                accept="application/json",
                contentType="application/json",
            )

            response_body = json.loads(response["body"].read())
            summary_text = self._extract_text(response_body)

            if summary_text:
                return summary_text.strip()
            else:
                raise ValueError("No assistant text found in response.")

        except (BotoCoreError, ClientError, ValueError, KeyError, TypeError) as e:
            print(f"Bedrock API problem: {e}.  Falling back to basic summary.")
            return self.generate_fallback_summary(clusters)

    #  Helpers: request / response
    def _build_request_body(self, system_prompt: str, user_prompt: str) -> dict:
        """
        Return the exact JSON payload required by the current `model_id`.
        * Amazon Nova → `schemaVersion: messages-v1`, `inferenceConfig`
        * Anthropic Claude → top-level OpenAI-style keys
        """
        if self.model_id.startswith("amazon.nova"):
            return {
                "schemaVersion": "messages-v1",
                "system": [{"text": system_prompt}],
                "messages": [
                    {"role": "user", "content": [{"text": user_prompt}]}
                ],
                "inferenceConfig": {
                    "maxTokens": 300,
                    "temperature": 0.5,
                    "topP": 0.9,
                },
            }
        else:  # default to Claude-family schema
            return {
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": user_prompt}],
                    }
                ],
                "max_tokens": 300,
                "temperature": 0.5,
                "top_p": 0.9,
                "anthropic_version": "bedrock-2023-05-31",
            }

    def _extract_text(self, body: dict) -> str | None:
        """
        Extract the assistant’s reply text regardless of provider envelope.
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

        return None

    #  Helpers: log-specific
    @staticmethod
    def _format_clusters_for_prompt(clusters: list) -> str:
        """
        Accepts a list of dicts **or** LogCluster dataclass instances and returns
        a human-readable block for the Claude prompt.
        """
        # small utility so we can handle both styles seamlessly
        def get_attr(obj, key):
            return obj[key] if isinstance(obj, dict) else getattr(obj, key)

        # sort by occurrence count, descending
        sorted_clusters = sorted(clusters, key=lambda c: get_attr(c, "count"), reverse=True)

        # one line per cluster
        lines = [
            f'- Signature: "{get_attr(c, "signature")}", Occurrences: {get_attr(c, "count")}'
            for c in sorted_clusters
        ]
        return "\n".join(lines)

    @staticmethod
    def generate_fallback_summary(clusters: List[dict]) -> str:
        """
        Deterministic summary used when Bedrock cannot be reached or parsed.
        """
        if not clusters:
            return "No errors detected."

        total_errors = sum(c["count"] for c in clusters)
        num_signatures = len(clusters)
        most_common = clusters[0]

        return (
            "AI summary failed. Basic Analysis: "
            f"Found {total_errors} errors across {num_signatures} unique signatures. "
            f"The most common error ({most_common["count"]} times) was: "
            f"'{most_common["signature"]}'."
        )
    