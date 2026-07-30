import smtplib
import html as _html
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from config.settings import settings

logger = logging.getLogger(__name__)

_SEVERITY_COLORS = {
    "critical": "#d73a49",
    "warning": "#b08800",
    "normal": "#22863a",
}


def _text_to_html(text: str) -> str:
    """Convert plain LLM alert text into readable HTML.

    - HTML-escapes the content
    - Splits blank-line-separated blocks into paragraphs
    - Turns single newlines into <br>
    - Renders leading "1." / "-" / "*" lines as list-ish bold leads
    """
    if not text:
        return "<p><em>No alert details available.</em></p>"

    blocks = re.split(r"\n\s*\n", text.strip())
    parts = []
    for block in blocks:
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        # Detect a list block (most lines start with a number or bullet)
        list_like = sum(bool(re.match(r"^(\d+[\.\)]|[-*•])\s+", ln)) for ln in lines)
        if lines and list_like >= max(1, len(lines) // 2):
            items = []
            for ln in lines:
                ln = re.sub(r"^(\d+[\.\)]|[-*•])\s+", "", ln)
                items.append(f"<li>{_html.escape(ln)}</li>")
            parts.append(f"<ul style='margin:8px 0;padding-left:20px'>{''.join(items)}</ul>")
        else:
            escaped = "<br>".join(_html.escape(ln) for ln in lines)
            parts.append(f"<p style='margin:8px 0;line-height:1.5'>{escaped}</p>")
    return "".join(parts)


def _runbook_to_html(runbook_ctx: str) -> str:
    if not runbook_ctx or not runbook_ctx.strip():
        return ""
    lines = []
    for ln in runbook_ctx.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("#"):
            heading = _html.escape(s.lstrip("#").strip())
            lines.append(f"<div style='font-weight:600;margin-top:8px'>{heading}</div>")
        elif s.startswith(("-", "*", "•")):
            lines.append(f"<div style='margin-left:14px'>• {_html.escape(s[1:].strip())}</div>")
        else:
            lines.append(f"<div>{_html.escape(s)}</div>")
    return "".join(lines)


def render_alert(details: dict, alert_text: str, runbook_ctx: str = "", reason: str = ""):
    """Build (html_body, text_body) for an alert email from structured event details."""
    classification = (details.get("classification") or "critical").lower()
    color = _SEVERITY_COLORS.get(classification, "#d73a49")
    source = f"{details.get('source_type', '')}/{details.get('source_name', '')}".strip("/")
    metric = details.get("metric_name", "")
    value = details.get("metric_value", "")
    confidence = details.get("confidence")
    conf_str = f"{confidence:.2f}" if isinstance(confidence, (int, float)) else "n/a"
    timestamp = details.get("timestamp", "")

    rows = [
        ("Source", source),
        ("Metric", metric),
        ("Value", value),
        ("Classification", classification.upper()),
        ("Confidence", conf_str),
        ("Detected at", timestamp),
    ]
    row_html = "".join(
        f"<tr><td style='padding:6px 12px;color:#586069;white-space:nowrap'>{_html.escape(str(k))}</td>"
        f"<td style='padding:6px 12px;font-weight:600'>{_html.escape(str(v))}</td></tr>"
        for k, v in rows
    )

    runbook_html = _runbook_to_html(runbook_ctx)
    runbook_section = (
        f"<h3 style='margin:18px 0 6px;font-size:14px;color:#24292e'>📘 Runbook guidance</h3>"
        f"<div style='background:#f6f8fa;border-radius:6px;padding:12px;font-size:13px;color:#24292e'>{runbook_html}</div>"
        if runbook_html else ""
    )
    reason_section = (
        f"<p style='margin:8px 0;font-size:13px;color:#586069'><strong>Why:</strong> {_html.escape(reason)}</p>"
        if reason else ""
    )

    html_body = f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;background:#f0f2f5;padding:20px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#24292e">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.1)">
    <div style="background:{color};color:#ffffff;padding:16px 20px">
      <div style="font-size:12px;letter-spacing:1px;opacity:0.85">AGENTIC MONITOR ALERT</div>
      <div style="font-size:20px;font-weight:700;margin-top:2px">{classification.upper()}: {_html.escape(str(source))}</div>
    </div>
    <div style="padding:20px">
      <table style="border-collapse:collapse;font-size:13px;margin-bottom:8px">{row_html}</table>
      {reason_section}
      <h3 style="margin:18px 0 6px;font-size:14px;color:#24292e">🔎 Analysis</h3>
      <div style="font-size:14px;color:#24292e">{_text_to_html(alert_text)}</div>
      {runbook_section}
    </div>
    <div style="padding:12px 20px;background:#f6f8fa;font-size:11px;color:#959da5;border-top:1px solid #e1e4e8">
      Generated automatically by Agentic Monitor. Reply is not monitored.
    </div>
  </div>
</body>
</html>"""

    # Plain-text alternative
    text_lines = [
        "AGENTIC MONITOR ALERT",
        f"{classification.upper()}: {source}",
        "",
        f"Metric:        {metric} = {value}",
        f"Classification: {classification.upper()} (confidence {conf_str})",
        f"Detected at:   {timestamp}",
    ]
    if reason:
        text_lines += ["", f"Why: {reason}"]
    text_lines += ["", "ANALYSIS", "--------", (alert_text or "").strip()]
    if runbook_ctx and runbook_ctx.strip():
        text_lines += ["", "RUNBOOK GUIDANCE", "----------------", runbook_ctx.strip()]
    text_lines += ["", "-- Generated automatically by Agentic Monitor."]
    text_body = "\n".join(text_lines)

    return html_body, text_body


def send_email(subject: str, html_body: str, to: str = None, text_body: str = None):
    to = to or settings.ALERT_EMAIL_TO
    if not to:
        logger.warning("No recipient configured for send_email")
        return False
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_USER
    msg["To"] = to
    # Order matters: last attached part is preferred by mail clients (HTML wins).
    if text_body:
        msg.attach(MIMEText(text_body, "plain"))
    msg.attach(MIMEText(html_body, "html"))
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as s:
            s.starttls()
            s.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            s.sendmail(settings.SMTP_USER, [to], msg.as_string())
        logger.info("Email sent to %s", to)
        return True
    except Exception as e:
        logger.exception("Failed to send email: %s", e)
        return False
