# lambda/send_alert/formatter.py
import json
from datetime import datetime
from html import escape

# Configuration
# Defines the appearance and keywords for different log levels.
# The keys are the canonical log levels.
LOG_LEVEL_CONFIG = {
    "CRITICAL": {"icon": "🔴", "css_class": "highlight-critical"},
    "FATAL":    {"icon": "🔴", "css_class": "highlight-fatal"},
    "ERROR":    {"icon": "🔴", "css_class": "highlight-error"},
    "WARNING":  {"icon": "🟡", "css_class": "highlight-warning"},
    "INFO":     {"icon": "🔵", "css_class": "highlight-info"},
    "DEBUG":    {"icon": "⚙️", "css_class": "highlight-debug"},
    "SERVICE":  {"icon": "🔧", "css_class": "highlight-service"},
}
DEFAULT_CONFIG = {"icon": "⚪️", "css_class": "highlight-general"}


# Private Helper Functions
def _parse_log_signature(signature: str) -> tuple[str, str, dict]:
    """
    Parses a log signature to extract its level, message, and configuration.
    
    Returns:
        A tuple containing (canonical_level, message, config_dict).
    """
    split_signature = signature.split(":", 1)
    category = split_signature[0].strip().upper()
    message = f"{split_signature[1].strip()}" if len(split_signature) == 2 else ""
    
    # Find the matching canonical level and its config
    for level, config in LOG_LEVEL_CONFIG.items():
        if level in category:
            return level, message, config
            
    # If no specific level is found, return the original category and default config
    return category, message, DEFAULT_CONFIG


def format_timestamp(iso_string: str) -> str:
    """
    Takes an ISO 8601 timestamp string and converts it to a more
    human-readable format, e.g., "YYYY-MM-DD HH:MM:SS UTC".
    Returns the original string if parsing fails.
    """
    if not iso_string:
        return "N/A"
    try:
        dt_object = datetime.fromisoformat(iso_string.replace('Z', '+00:00'))
        return dt_object.strftime('%Y-%m-%d %H:%M:%S %Z')
    except (ValueError, TypeError):
        return iso_string


# HTML Formatting
def _build_html_styles() -> str:
    """Returns the CSS styles for the HTML email."""
    return """
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #24292e; background-color: #f6f8fa; margin: 0; padding: 20px;}
        .container { border: 1px solid #e1e4e8; padding: 0; max-width: 700px; margin: 0 auto; border-radius: 8px; background-color: #ffffff; box-shadow: 0 4px 12px rgba(27,31,35,0.08); }
        .header { background-color: #24292e; color: white; padding: 24px; text-align: center; border-radius: 8px 8px 0 0; }
        .header h1 { margin: 0; font-size: 28px; letter-spacing: -1px; }
        .content { padding: 24px; }
        h3 { border-bottom: 1px solid #e1e4e8; padding-bottom: 10px; margin-top: 24px; font-size: 20px; font-weight: 600; }
        .ai-summary { background-color: #f1f8ff; border: 1px solid #c8e1ff; border-radius: 6px; margin-bottom: 24px; }
        .ai-summary-header { display: flex; align-items: center; padding: 12px 16px; border-bottom: 1px solid #c8e1ff; font-weight: 600; color: #032f62; }
        .ai-summary-body { padding: 16px; font-size: 15px; color: #032f62; font-style: italic; }
        .header-table { width: 100%; border-collapse: collapse; }
        .header-table td { vertical-align: middle; }
        .header-table .signature-cell { text-align: left; }
        .header-table .badge-cell { text-align: right; width: 1%; }
        .cluster-card { border: 1px solid #e1e4e8; border-radius: 6px; margin-bottom: 16px; overflow: hidden; }
        .cluster-header { display: flex; justify-content: space-between; align-items: center; background-color: #f6f8fa; padding: 10px 15px; font-weight: 600; border-bottom: 1px solid #e1e4e8; }
        .cluster-body { padding: 15px; }
        .count-badge { background-color: #586069; color: white; padding: 4px 10px; font-size: 12px; font-weight: 600; border-radius: 2em; white-space: nowrap; }
        pre { margin: 10px 0 0 0; padding: 10px; background-color: #f6f8fa; border-radius: 6px; white-space: pre-wrap; word-wrap: break-word; font-family: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, Courier, monospace; font-size: 14px;}
        .highlight-critical, .highlight-fatal, .highlight-error { color: #d73a49; font-weight: bold; font-size: 18px}
        .highlight-warning { color: #b08800; font-weight: bold; font-size: 18px}
        .highlight-info {color: #007bff; font-weight: bold; font-size: 18px;}
        .highlight-debug {color: #6c757d; font-weight: normal; font-size: 18px;}
        .highlight-service { color: #6f42c1; font-weight: bold; font-size: 18px;}
        .highlight-general { color: #4a4a4a; font-weight: bold; font-size: 18px}
        .footer { text-align: center; font-size: 14px; color: #6a737d; padding: 20px;}
    </style>
    """

def _build_html_cluster_card(cluster: dict) -> str:
    """Builds the HTML for a single cluster card."""
    signature = cluster.get("signature", "N/A")
    count = cluster.get("count", 0)
    rep_log = cluster.get("representative_log", "N/A")

    level, message, config = _parse_log_signature(signature)
    status_icon = config["icon"]
    css_class = config["css_class"]
    
    # Use html.escape for security on all user-controlled content
    safe_level = escape(level)
    safe_message = escape(message)
    
    highlighted_signature = f"<span class='{css_class}'>{safe_level}{': ' if safe_message else ''}</span>{safe_message}"

    return f"""
    <div class="cluster-card">
        <div class="cluster-header">
            <table class="header-table">
                <tr>
                    <td class="signature-cell">{status_icon} <code>{highlighted_signature}</code></td>
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

def format_html_body(analysis_result: dict, curr_num: int, total_num: int) -> str:
    """Takes the full analysis result and builds a final, polished HTML digest email."""
    styles = _build_html_styles()
    
    # AI Summary Card
    ai_summary_html = ""
    if ai_summary := analysis_result.get("summary"):
        ai_summary_html = f"""
        <div class="ai-summary">
            <div class="ai-summary-header"><span>💡 AI-Generated Summary</span></div>
            <div class="ai-summary-body">{escape(ai_summary)}</div>
        </div>
        """
    
    # Cluster Cards
    cluster_cards = "".join(_build_html_cluster_card(c) for c in analysis_result.get("clusters", []))
    
    # Footer
    processed_at = format_timestamp(analysis_result.get("processed_at", "N/A"))
    analysis_id = analysis_result.get("analysis_id", "N/A")
    footer_html = f'<div class="footer">Analysis ID: {analysis_id}<br/>Processed At: {processed_at}</div>'

    # Assemble Final HTML
    total_logs = analysis_result.get("total_logs_processed", 0)
    total_clusters = analysis_result.get("total_clusters_found", 0)
    html_title = "📑 Log Analysis Digest"
    if total_num >  1:
        html_title += f" ({curr_num}/{total_num})"
    
    return f"""
    <html><head><title>{html_title}</title>{styles}</head><body>
        <div class="container">
            <div class="header"><h1>{html_title}</h1></div>
            <div class="content">
                <p>An analysis of recent logs has been completed. Found <strong>{total_clusters}</strong> unique error patterns across <strong>{total_logs}</strong> total logs.</p>
                {ai_summary_html}
                <h3>Detected Error Clusters</h3>
                {cluster_cards}
            </div>
            {footer_html}
        </div>
    </body></html>
    """


# Slack Formatting
def format_slack_message(analysis_result: dict, curr_num: int, total_num: int) -> dict:
    """Builds a Slack message using Block Kit."""
    total_clusters = analysis_result.get("total_clusters_found", 0)
    total_logs = analysis_result.get("total_logs_processed", 0)
    analysis_id = analysis_result.get("analysis_id", "N/A")
    timestamp = analysis_result.get("processed_at", "N/A")

    blocks = [{
        "type": "header",
         "text": {"type": "plain_text",
                  "text": f":rotating_light: Log Analysis Digest{f" ({curr_num}/{total_num})" if (total_num > 1) else ""}",
                  "emoji": True}
        }]
    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"Found *{total_clusters}* unique patterns across *{total_logs}* total logs."}})

    if ai_summary := analysis_result.get("summary"):
        blocks.extend([{"type": "section", "text": {"type": "mrkdwn", "text": f"💡 *AI Summary:*\n>_{escape(ai_summary)}_"}}])
    
    blocks.append({"type": "divider"})

    for cluster in analysis_result.get("clusters", []):
        signature = cluster.get("signature", "N/A")
        count = cluster.get("count", 0)
        rep_log = cluster.get("representative_log", "N/A")
        
        level, message, config = _parse_log_signature(signature)
        status_icon = config["icon"]

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"{status_icon} *{level}{':' if message else ''}* {message}"},
            "accessory": {"type": "button", "text": {"type": "plain_text", "text": f"Count: {count}", "emoji": True}, "value": "count_button"}
        })
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": f"*Representative Log:*\n```{rep_log}```"}})
        blocks.append({"type": "divider"})

    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": f"Analysis ID: `{analysis_id}` | Processed At: `{format_timestamp(timestamp)}`"}]})
    return {"blocks": blocks}


# Plain Text Formatting
def format_text_body(analysis_result: dict) -> str:
    """Creates a plain text version of the digest."""
    total_clusters = analysis_result.get("total_clusters_found", 0)
    total_logs = analysis_result.get("total_logs_processed", 0)
    timestamp = format_timestamp(analysis_result.get("processed_at", "N/A"))

    lines = [
        f"Log Analysis Digest: {total_clusters} unique error patterns found across {total_logs} total logs.",
        "==================================================",
    ]
    
    if ai_summary := analysis_result.get("summary"):
        lines.append(f"AI Summary:\n{ai_summary}\n")

    for i, cluster in enumerate(analysis_result.get("clusters", [])):
        lines.append(f"--- Cluster #{i+1} ---")
        lines.append(f"Signature: {cluster.get('signature', 'N/A')}")
        lines.append(f"Count: {cluster.get('count', 0)}")
        lines.append(f"Representative Log: {cluster.get('representative_log', 'N/A')}\n")
    
    lines.append(f"Analysis ID: {analysis_result.get('analysis_id', 'N/A')}")
    lines.append(f"Processed At: {timestamp}")
        
    return "\n".join(lines)
