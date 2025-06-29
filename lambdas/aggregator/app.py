# lambda/aggregator/app.py
import os
import json
import boto3
from collections import defaultdict
from datetime import datetime, timezone

# Assuming bedrock_summarizer is in a common Lambda Layer
from bedrock_summarizer import BedrockSummarizer

# --- Configuration ---
try:
    FINAL_ALERTS_TOPIC_ARN = os.environ['FINAL_ALERTS_TOPIC_ARN']
    SNS_CLIENT = boto3.client('sns')
except KeyError as e:
    print(f"FATAL: Missing required environment variable: {e}")
    SNS_CLIENT = None

def merge_analysis_results(records: list[dict]) -> dict:
    """
    Parses SQS records, merges multiple analysis results, and generates a master summary.
    """
    all_clusters = {}
    total_logs = 0
    all_summaries = []
    analysis_id = "consolidated-digest"

    print(f"Aggregating results from {len(records)} SQS messages...")

    for record in records:
        try:
            body_str = record.get('body', '{}')
            body_data = json.loads(body_str)
            
            # Handle both direct SQS and SNS-to-SQS messages
            if 'Message' in body_data:
                # This handles messages coming from an SNS topic subscription
                analysis_result = json.loads(body_data['Message'])
            else:
                # This handles messages sent directly to SQS from the filter
                analysis_result = body_data
            
            total_logs += analysis_result.get("total_logs_processed", 0)
            if analysis_id == "consolidated-digest" and analysis_result["analysis_id"]:
                analysis_id += analysis_result["analysis_id"]
            if summary := analysis_result.get("summary"):
                all_summaries.append(summary)

            # Merge clusters, consolidating counts for the same signature
            for cluster in analysis_result.get("clusters", []):
                sig = cluster.get("signature")
                # if cluster.get("count", 0) < 100: break # for testing
                if not sig: continue
                if sig not in all_clusters:
                    all_clusters[sig] = cluster
                else:
                    all_clusters[sig]["count"] += cluster.get("count", 0)

        except (KeyError, json.JSONDecodeError, TypeError) as e:
            print(f"⚠️ Warning: Could not parse a record from SQS. Skipping. Error: {e}")
            continue

    sorted_clusters = sorted(all_clusters.values(), key=lambda c: c.get("count", 0), reverse=True)
    
    # Generate the single, high-level summary using the common BedrockSummarizer
    final_summary = ""
    if all_summaries:
        try:
            summarizer = BedrockSummarizer()
            final_summary = summarizer.synthesize_summaries(all_summaries)
            print("Successfully generated master summary.")
        except Exception as e:
            print(f"⚠️ Could not generate master summary: {e}. Falling back to joining summaries.")
            final_summary = "\n\n---\n\n".join(all_summaries)
    
    return {
        "analysis_id": analysis_id,
        "summary": final_summary,
        "clusters": sorted_clusters,
        "total_clusters_found": len(sorted_clusters),
        "total_logs_processed": total_logs,
        "processed_at": datetime.now(timezone.utc).isoformat()
    }


def handler(event, context):
    """
    Main Lambda handler triggered by SQS. Aggregates results and forwards a
    single, consolidated report to the final alert topic.
    """
    if not SNS_CLIENT:
        print("FATAL: SNS client not initialized. Aborting.")
        return {"statusCode": 500}

    records = event.get('Records', [])
    if not records:
        print("ℹ️ No records to process. Exiting.")
        return {"statusCode": 200}

    # Step 1: Aggregate all results from the SQS batch
    consolidated_result = merge_analysis_results(records)

    if not consolidated_result or not consolidated_result.get("clusters"):
        print("ℹ️ No actionable clusters found after aggregation. Nothing to forward.")
        return {"statusCode": 200}

    # Step 2: Publish the single, consolidated report to the final SNS topic
    try:
        print(f"Forwarding consolidated report with {consolidated_result['total_clusters_found']} clusters to the final alert topic...")
        SNS_CLIENT.publish(
            TopicArn=FINAL_ALERTS_TOPIC_ARN,
            Message=json.dumps(consolidated_result, default=str),
            Subject="Consolidated Log Analysis Alert"
        )
        print("✅ Successfully published consolidated report.")
    except Exception as e:
        print(f"❌ CRITICAL: Failed to publish consolidated report to SNS. Error: {e}")
        # Re-raise the exception to ensure the message is not lost from the SQS queue
        raise e

    return {"statusCode": 200}
