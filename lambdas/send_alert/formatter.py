# lambda/send_alert/formatter.py
import json
from datetime import datetime, timezone
from html import escape

def format_timestamp(iso_string: str) -> str:
    """
    Takes an ISO 8601 timestamp string and converts it to a more
    human-readable format, e.g., "YYYY-MM-DD HH:MM:SS UTC".
    Returns the original string if parsing fails.
    """
    if not iso_string:
        return "N/A"
    try:
        # Parse the ISO format string into a datetime object
        # The 'Z' at the end stands for Zulu time, which is UTC.
        dt_object = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        # Format it into the desired string format
        return dt_object.strftime('%Y-%m-%d %H:%M:%S %Z')
    except (ValueError, TypeError):
        # If parsing fails for any reason, return the original string
        return iso_string
    
def format_html_body(analysis_result: dict) -> str:
    """Takes the full analysis result and builds a final, polished HTML digest email."""

    # --- 1. CSS Styles ---
    # Added styles for count badges and a more distinct AI summary
    styles = """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #24292e; background-color: #f6f8fa; margin: 0; padding: 20px;}
        .container { border: 1px solid #e1e4e8; padding: 0; max-width: 700px; margin: 0 auto; border-radius: 8px; background-color: #ffffff; box-shadow: 0 4px 12px rgba(27,31,35,0.08); }
        .header { background-color: #24292e; color: white; padding: 24px; text-align: center; border-radius: 8px 8px 0 0; }
        .header h1 { margin: 0; font-size: 28px; letter-spacing: -1px; }
        .content { padding: 24px; }

        h3 { border-bottom: 1px solid #e1e4e8; padding-bottom: 10px; margin-top: 24px; font-size: 20px; font-weight: 600; }
        .ai-summary {
            background-color: #f1f8ff;
            border: 1px solid #c8e1ff;
            border-radius: 6px;
            margin-bottom: 24px;
        }
        .ai-summary-header {
            display: flex;
            align-items: center;
            padding: 12px 16px;
            border-bottom: 1px solid #c8e1ff;
            font-weight: 600;
            color: #032f62;
        }
        .ai-summary-header .icon {
            font-size: 20px;
            margin-right: 8px;
        }
        .ai-summary-body {
            padding: 16px;
            font-size: 15px;
            color: #032f62;
            font-style: italic;
        }

        .header-table { width: 100%; border-collapse: collapse; }
        .header-table td { vertical-align: middle; }
        .header-table .signature-cell { text-align: left; }
        .header-table .badge-cell { text-align: right; width: 1%; } /* The width:1% is a trick to make it only as wide as its content */

        .cluster-card { border: 1px solid #e1e4e8; border-radius: 6px; margin-bottom: 16px; overflow: hidden; }
        .cluster-header { display: flex; justify-content: space-between; align-items: center; background-color: #f6f8fa; padding: 10px 15px; font-weight: 600; border-bottom: 1px solid #e1e4e8; }
        .cluster-body { padding: 15px; }
        .count-badge {
            background-color: #586069; 
            color: white; 
            padding: 4px 10px; 
            font-size: 12px; 
            font-weight: 600; 
            border-radius: 2em;
            white-space: nowrap;
        }
        pre, code { font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace; font-size: 14px;}
        pre { margin: 10px 0 0 0; padding: 10px; background-color: #f6f8fa; border-radius: 6px; white-space: pre-wrap; word-wrap: break-word; }
        .highlight-critical, .highlight-error { color: #d73a49; font-weight: bold; font-size: 18px}
        .highlight-error, .highlight-error { color: #d73a49; font-weight: bold; font-size: 18px}
        .highlight-warning { color: #b08800; font-weight: bold; font-size: 18px}
        .highlight-general { color: #4a4a4a; font-weight: bold; font-size: 18px}
        .footer { text-align: center; font-size: 14px; color: #6a737d; padding: 20px; }
    </style>
    """

    # --- 2. Simple Syntax Highlighter ---
    def highlight_signature(signature_string):
        s = escape(str(signature_string)) # Use html.escape for security
        category = s.upper()
        if any(keyword in category for keyword in ("CRITICAL", "ERROR", "WARNING")):
            category = category.replace("CRITICAL", "<span class='highlight-critical'>Critical</span>")
            category = category.replace("ERROR", "<span class='highlight-error'>Error</span>")
            category = category.replace("WARNING", "<span class='highlight-warning'>Warning</span>")
        else:
            category = f"<span class='highlight-general'>{category}</span>"
        return category


    # --- 3. Build HTML Components ---

    # AI Summary Card
    ai_summary = analysis_result.get("summary")
    ai_summary_html = ""
    if ai_summary:
        ai_summary_html = f"""
        <div class="ai-summary">
            <div class="ai-summary-header">
                <span>💡 AI-Generated Summary</span>
            </div>
            <div class="ai-summary-body">
                {escape(ai_summary)}
            </div>
        </div>
        """
    
    # Cluster Cards
    clusters_html = ""
    for cluster in analysis_result.get("clusters", []):
        signature = cluster.get("signature", "N/A")
        count = cluster.get("count", 0)
        rep_log = cluster.get("representative_log", "N/A")
        
        # Add a status icon based on the signature
        status_icon = ""
        level = signature.upper()
        if "CRITICAL" in level or "ERROR" in level:
            status_icon = "🔴"
        elif "WARNING" in level:
            status_icon = "🟡"

        clusters_html += f"""
        <div class="cluster-card">
            <div class="cluster-header">
                <table class="header-table">
                    <tr>
                        <td class="signature-cell">{status_icon} <code>{highlight_signature(signature)}</code></td>
                        <td class="badge-cell"><span class="count-badge">Count: {count}</span></td>
                    </tr>
                </table>
            </div>
            <div class="cluster-body">
                <strong>Representative Log:</strong>
                <pre>{escape(rep_log)}</pre>
            </div>
        </div>
        """

    # Footer
    processed_at = format_timestamp(analysis_result.get("processed_at", "N/A"))
    analysis_id = analysis_result.get("analysis_id", "N/A")
    footer_html = f'<div class="footer">Analysis ID: {analysis_id}<br/>Processed At: {processed_at}</div>'

    # --- 4. Assemble Final HTML ---
    total_logs = analysis_result.get("total_logs_processed", 0)
    total_clusters = analysis_result.get("total_clusters_found", 0)
    html_title = "📑 Log Analysis Digest"
    
    html = f"""
    <html><head><title>{html_title}</title>{styles}</head><body>
        <div class="container">
            <div class="header"><h1>{html_title}</h1></div>
            <div class="content">
                <p>An analysis of recent logs has been completed. Found <strong>{total_clusters}</strong> unique error patterns across <strong>{total_logs}</strong> total logs.</p>
                {ai_summary_html}
                <h3>Detected Error Clusters</h3>
                {clusters_html}
            </div>
            {footer_html}
        </div>
    </body></html>
    """
    return html


def format_slack_message(analysis_result: dict) -> dict:
    """
    Takes the full analysis result and builds a final, polished Slack message
    with the count badge aligned to the right.
    """
    
    total_clusters = analysis_result.get("total_clusters_found", 0)
    total_logs = analysis_result.get("total_logs_processed", 0)
    analysis_id = analysis_result.get("analysis_id", "N/A")
    timestamp = analysis_result.get("processed_at", "N/A")
    ai_summary = analysis_result.get("summary")

    # --- Start building the Slack Blocks ---
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f":rotating_light: Log Analysis Digest: {total_clusters} Unique Error Patterns Found Across {total_logs} Total Logs",
                "emoji": True
            }
        }
    ]

    # Add AI Summary if it exists
    if ai_summary:
        blocks.extend([
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"💡 *AI Summary:*\n>_{ai_summary}_"}
            }
        ])
    
    blocks.append({"type": "divider"})

    # Add a card for each cluster
    for cluster in analysis_result.get("clusters", []):
        signature = cluster.get("signature", "N/A")
        count = cluster.get("count", 0)
        rep_log = cluster.get("representative_log", "N/A")
        
        # Determine the icon based on the signature
        status_icon = ""
        level = signature.capitalize()
        if "Critical" in level or "Error" in level:
            status_icon = "🔴"
        elif "Warning" in level:
            status_icon = "🟡"
        else:
            level = f"[{level}]"

        # This block uses an 'accessory' to place the button on the right.
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{status_icon} *{level}*"
            },
            "accessory": {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": f"Count: {count}",
                    "emoji": True
                },
                "value": "count_button" # A value is required for buttons
            }
        })
        
        # Add the representative log in its own section with a code block
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Representative Log:*\n```{rep_log}```"
            }
        })

        blocks.append({"type": "divider"})

    # Add the final footer
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": f"Analysis ID: `{analysis_id}`\nProcessed At: `{format_timestamp(timestamp)}`"}]})
    return {"blocks": blocks}


def format_text_body(analysis_result: dict) -> str:
    """Creates a plain text version of the digest email."""
    total_clusters = analysis_result.get("total_clusters_found", 0)
    total_logs = analysis_result.get("total_logs_processed", 0)
    analysis_id = analysis_result.get("analysis_id", "N/A")
    timestamp = format_timestamp(analysis_result.get("processed_at", "N/A"))

    text = f"Log Analysis Digest: {total_clusters} unique error patterns found across {total_logs} total logs.\n\n"
    
    for i, cluster in enumerate(analysis_result.get("clusters", [])):
        text += f"--- Cluster #{i+1} ---\n"
        text += f"Signature: {cluster.get('signature', 'N/A')}\n"
        text += f"Count: {cluster.get('count', 0)}\n"
        text += f"Representative Log: {cluster.get('representative_log', 'N/A')}\n\n"
    
    text += f"Analysis ID: {analysis_id}"
    text += f"Processed At: {timestamp}"
        
    return text