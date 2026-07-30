#!/usr/bin/env python3
"""
Agentic Monitor — Status digest demo.

Fetches a single URL (default: https://formatjsononline.com/api/status) and
emails you the live payload. Unlike scripts/demo.py this does NOT exercise
the classification/RAG/alert pipeline — it is a one-shot status snapshot.

Usage:
    .venv/bin/python demo.py
    .venv/bin/python demo.py --url https://example.com/api/health --to a@b.com
    .venv/bin/python demo.py --no-email        # print the payload, don't send
"""
import argparse
import html
import json
import os
import re
import sys
from datetime import datetime
from typing import Optional

import httpx

# Make project root importable regardless of cwd
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# --- Pretty console output ---------------------------------------------------

def banner(title: str):
    line = "═" * max(60, len(title) + 4)
    print(f"\n{line}\n  {title}\n{line}")


def step(num: int, title: str):
    print(f"\n── Step {num}: {title} " + "─" * (50 - len(title)))


def ok(msg: str):
    print(f"   ✓ {msg}")


def info(msg: str):
    print(f"   ℹ {msg}")


def fail(msg: str):
    print(f"   ✗ {msg}")


# --- Steps -------------------------------------------------------------------

DEFAULT_URL = "https://formatjsononline.com/api/orders"


def step1_fetch(url: str, timeout: float = 10.0):
    step(1, f"Fetch {url}")
    started = datetime.utcnow()
    try:
        r = httpx.get(url, timeout=timeout, follow_redirects=True)
        elapsed_ms = int(r.elapsed.total_seconds() * 1000)
        info(f"HTTP {r.status_code} in {elapsed_ms} ms")
        # Try to parse JSON; fall back to raw text
        try:
            payload = r.json()
            ok("Parsed JSON response")
            return {"ok": True, "status_code": r.status_code,
                    "elapsed_ms": elapsed_ms, "payload": payload,
                    "started_at": started.isoformat()}
        except ValueError:
            ok("Non-JSON response body captured as text")
            return {"ok": True, "status_code": r.status_code,
                    "elapsed_ms": elapsed_ms, "payload": r.text,
                    "started_at": started.isoformat()}
    except Exception as e:
        fail(f"Request failed: {e}")
        return {"ok": False, "error": str(e), "started_at": started.isoformat()}


def _status_field(payload):
    """Best-effort pull of api.status from the response payload."""
    if not isinstance(payload, dict):
        return None
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    api = data.get("api") if data else None
    return api.get("status") if isinstance(api, dict) else None


def _summarize(payload):
    if payload is None:
        return "", []

    # Non-dict payloads (lists, scalars, strings): compact one-liner
    if not isinstance(payload, dict):
        if isinstance(payload, list):
            return "", [f"  payload: list of {len(payload)} item(s)"]
        return "", [f"  payload: {type(payload).__name__} = {payload!r:.80}"]

    insights: dict[str, object] = {}

    # Known-shape branch: data.api.status etc.
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if isinstance(data, dict) and isinstance(data.get("api"), dict):
        api = data["api"]
        if "status" in api:
            insights["API status"] = api.get("status")
        if "uptime" in api:
            insights["Uptime"] = api.get("uptime")
        rt = api.get("responseTime")
        if isinstance(rt, dict):
            unit = rt.get("unit", "ms")
            parts = []
            for key in ("average", "p95", "p99"):
                if rt.get(key) is not None:
                    parts.append(f"{key}={rt[key]} {unit}")
            if parts:
                insights["Response time"] = " · ".join(parts)

    if isinstance(data, dict) and isinstance(data.get("statistics"), dict):
        stats = data["statistics"]
        for k in ("totalRequests", "requestsToday", "requestsThisHour",
                 "activeUsers", "totalUsers"):
            if k in stats:
                # Make camelCase readable
                insights[f"Stats · {k}"] = stats[k]

    if isinstance(data, dict) and isinstance(data.get("endpoints"), list):
        eps = data["endpoints"]
        if eps:
            ops = sum(1 for e in eps
                      if isinstance(e, dict) and e.get("status") == "operational")
            insights["Endpoints"] = f"{ops}/{len(eps)} operational"

    if isinstance(data, dict) and isinstance(data.get("incidents"), list):
        incidents = data["incidents"]
        open_n = sum(1 for i in incidents
                     if isinstance(i, dict) and i.get("status") != "resolved")
        if incidents:
            insights["Incidents"] = f"{open_n} open / {len(incidents)} total"

    if isinstance(data, dict) and isinstance(data.get("maintenance"), dict):
        m = data["maintenance"]
        if m.get("scheduled"):
            insights["Maintenance"] = f"scheduled — {m.get('nextWindow', 'window TBD')}"
        elif m.get("nextWindow"):
            insights["Next maintenance"] = m.get("nextWindow")

    # Generic fallback: top-level keys + types (only when known-shape branch found nothing)
    if not insights:
        for k, v in payload.items():
            if k == "meta":
                continue
            if isinstance(v, dict):
                insights[str(k)] = f"object ({len(v)} keys)"
            elif isinstance(v, list):
                insights[str(k)] = f"array ({len(v)} item(s))"
            elif isinstance(v, bool):
                insights[str(k)] = str(v)
            elif isinstance(v, (int, float)):
                insights[str(k)] = v
            elif isinstance(v, str):
                insights[str(k)] = v[:80] + ("…" if len(v) > 80 else "")

    if not insights:
        return "", []

    # --- HTML snippet ---
    rows = "".join(
        f"<tr><td style='padding:6px 12px;color:#586069'>{html.escape(str(k))}</td>"
        f"<td style='padding:6px 12px;font-weight:600'>"
        f"{html.escape(str(v))}</td></tr>"
        for k, v in insights.items()
    )
    html_snippet = (
        "<h3 style='margin:14px 0 6px;font-size:14px;color:#24292e'>📊 Insights</h3>"
        "<table style='border-collapse:collapse;font-size:13px;margin-bottom:14px;width:100%'>"
        f"{rows}</table>"
    )

    # --- Plain-text lines ---
    text_lines = ["", "INSIGHTS", "--------"]
    for k, v in insights.items():
        text_lines.append(f"  {k}: {v}")

    return html_snippet, text_lines


def _build_analysis_prompt(payload, url: str, status_code, elapsed_ms) -> str:
    """Construct a payload-aware prompt for the LLM."""
    if isinstance(payload, (dict, list)):
        try:
            payload_str = json.dumps(payload, indent=2, ensure_ascii=False)
        except (TypeError, ValueError):
            payload_str = str(payload)
    else:
        payload_str = str(payload) if payload is not None else "(empty body)"
    # Bound the prompt so we don't blow the LLM's context window
    max_chars = 4000
    if len(payload_str) > max_chars:
        payload_str = payload_str[:max_chars] + f"\n... [truncated, {len(payload_str) - max_chars} more chars]"
    rt = f"{elapsed_ms} ms" if elapsed_ms is not None else "unknown"
    return (
        "You are an operations analyst writing a brief AI analysis for an email digest.\n"
        f"A monitoring agent just fetched {url} and got HTTP {status_code} in {rt}.\n"
        "Here is the response payload:\n\n"
        f"{payload_str}\n\n"
        "Write a concise analysis (under 180 words) covering:\n"
        "1. What this endpoint appears to do and its current state\n"
        "2. Any notable signals (status flags, thresholds, errors, anomalies, maintenance windows)\n"
        "3. Whether this looks healthy or concerning, and why\n"
        "Use short bullet points. Plain English. No preamble."
    )


def _ai_analyze(payload, url: str, status_code, elapsed_ms) -> tuple[str, list[str]]:
    """Return (html_snippet, text_lines) for the AI Analysis card.

    Gracefully degrades silently if the LLM provider is unreachable.
    """
    from agent.alert_generator import generate_text

    prompt = _build_analysis_prompt(payload, url, status_code, elapsed_ms)
    info("Calling LLM for AI analysis (provider configured in .env) ...")
    print("   ⏳ Generating AI analysis ...", end="", flush=True)
    text = generate_text(prompt, fallback="")
    print("\r" + " " * 60 + "\r", end="")

    if not text:
        fail("LLM unavailable — skipping AI Analysis (insights/email still sent)")
        return "", []

    text = text.strip()
    ok(f"AI analysis: {len(text)} chars")

    blocks = re.split(r"\n\s*\n", text)
    parts = []
    for b in blocks:
        lines = [html.escape(ln) for ln in b.splitlines() if ln.strip()]
        if not lines:
            continue
        list_like = sum(1 for ln in lines if re.match(r"^(\d+[\.\)]|[-*•])\s+", ln))
        if list_like >= max(1, len(lines) // 2):
            items = []
            for ln in lines:
                ln = re.sub(r"^(\d+[\.\)]|[-*•])\s+", "", ln)
                items.append(f"<li>{ln}</li>")
            parts.append(f"<ul style='margin:8px 0;padding-left:20px'>{''.join(items)}</ul>")
        else:
            joined = "<br>".join(lines)
            parts.append(f"<p style='margin:8px 0;line-height:1.5'>{joined}</p>")
    analysis_html = (
        "<h3 style='margin:14px 0 6px;font-size:14px;color:#24292e'>🤖 AI Analysis</h3>"
        "<div style='background:#f3eefe;border-left:3px solid #6f42c1;padding:12px 14px;"
        "border-radius:6px;font-size:13px;color:#24292e;line-height:1.5'>"
        f"{''.join(parts)}</div>"
    )

    text_lines = ["", "AI ANALYSIS", "------------", text]
    return analysis_html, text_lines


def step2_build_email(result: dict, url: str, include_insights: bool = True,
                      ai_html: str = "", ai_text=None):
    if ai_text is None:
        ai_text = []



    from config.settings import settings

    fetched_at = result.get("started_at", datetime.utcnow().isoformat())
    status_code = result.get("status_code")
    elapsed_ms = result.get("elapsed_ms")
    payload = result.get("payload")
    err = result.get("error")

    # Header classification just drives the color
    if not result.get("ok"):
        verdict = "ERROR"
        color = "#d73a49"
    elif status_code and 200 <= status_code < 300:
        # Prefer the API's own status field if present
        api_status = _status_field(payload) if isinstance(payload, dict) else None
        verdict = (api_status or "OK").upper()
        color = "#22863a" if verdict in ("OK", "OPERATIONAL") else "#b08800"
    else:
        verdict = f"HTTP {status_code or '?'}"
        color = "#d73a49"

    subject = f"[{verdict}] {url}"

    # --- HTML body -----------------------------------------------------------
    if err:
        detail_html = (
            f"<p style='margin:8px 0;color:#d73a49'><strong>Error:</strong> "
            f"{html.escape(err)}</p>"
        )
    elif isinstance(payload, (dict, list)):
        body_json = json.dumps(payload, indent=2, ensure_ascii=False)
        detail_html = (
            "<pre style='background:#f6f8fa;padding:14px;border-radius:6px;"
            "font-size:12px;line-height:1.45;overflow:auto;color:#24292e'>"
            f"{html.escape(body_json)}</pre>"
        )
    else:
        body_text = str(payload)[:6000]
        detail_html = (
            "<pre style='background:#f6f8fa;padding:14px;border-radius:6px;"
            f"font-size:12px;color:#24292e'>{html.escape(body_text)}</pre>"
        )

    meta_rows = [
        ("URL", url),
        ("Verdict", verdict),
        ("HTTP status", status_code if status_code else "—"),
        ("Response time", f"{elapsed_ms} ms" if elapsed_ms is not None else "—"),
        ("Fetched at (UTC)", fetched_at),
        ("Recipient", settings.ALERT_EMAIL_TO or "(not configured)"),
    ]
    rows_html = "".join(
        f"<tr><td style='padding:6px 12px;color:#586069;white-space:nowrap'>"
        f"{html.escape(str(k))}</td>"
        f"<td style='padding:6px 12px;font-weight:600'>"
        f"{html.escape(str(v))}</td></tr>"
        for k, v in meta_rows
    )

    insights_html, insights_text = ("", [])
    if include_insights and payload is not None:
        insights_html, insights_text = _summarize(payload)

    html_body = f"""\
<!DOCTYPE html>
<html>
<body style="margin:0;background:#f0f2f5;padding:20px;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#24292e">
  <div style="max-width:680px;margin:0 auto;background:#ffffff;border-radius:8px;overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,0.1)">
    <div style="background:{color};color:#ffffff;padding:16px 20px">
      <div style="font-size:12px;letter-spacing:1px;opacity:0.85">AGENTIC MONITOR — STATUS DIGEST</div>
      <div style="font-size:20px;font-weight:700;margin-top:2px">{html.escape(verdict)}: {html.escape(url)}</div>
    </div>
    <div style="padding:20px">
      <table style="border-collapse:collapse;font-size:13px;margin-bottom:14px">{rows_html}</table>
      {insights_html}
      {ai_html}
      <h3 style="margin:14px 0 6px;font-size:14px;color:#24292e">📦 Response body</h3>
      {detail_html}
    </div>
    <div style="padding:12px 20px;background:#f6f8fa;font-size:11px;color:#959da5;border-top:1px solid #e1e4e8">
      Generated by Agentic Monitor — demo.py. Reply is not monitored.
    </div>
  </div>
</body>
</html>"""

    # --- Plain-text body -----------------------------------------------------
    text_lines = [
        "AGENTIC MONITOR — STATUS DIGEST",
        f"{verdict}: {url}",
        "",
        f"HTTP status:    {status_code if status_code else '-'}",
        f"Response time:  {elapsed_ms} ms" if elapsed_ms is not None else "Response time:  -",
        f"Fetched at:     {fetched_at}",
    ] + insights_text + ai_text
    if err:
        text_lines += ["", f"Error: {err}"]
    elif isinstance(payload, (dict, list)):
        text_lines += ["", "RESPONSE BODY", "-------------", json.dumps(payload, indent=2, ensure_ascii=False)]
    else:
        body_text = str(payload)[:6000]
        text_lines += ["", "RESPONSE BODY", "-------------", body_text]
    text_lines += ["", "-- Generated automatically by Agentic Monitor."]
    text_body = "\n".join(text_lines)

    return subject, html_body, text_body


def step3_send(subject: str, html_body: str, text_body: str, to: str | None, do_send: bool):
    step(3, "Send via SMTP")
    if not do_send:
        info("--no-email set — payload shown above only")
        return True

    from notifications.email_notifier import send_email
    print("   ⏳ Sending ...", end="", flush=True)
    sent = send_email(subject=subject, html_body=html_body, text_body=text_body, to=to)
    print("\r" + " " * 60 + "\r", end="")
    if sent:
        ok(f"Email sent: \"{subject}\"")
        if to:
            info(f"Delivered to: {to}")
        return True
    fail("Email send failed — check SMTP_HOST/SMTP_USER/SMTP_PASSWORD in .env")
    return False


# --- Main --------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Fetch a URL and email the live payload.")
    parser.add_argument("--url", default=DEFAULT_URL, help="URL to probe")
    parser.add_argument("--to", default=None, help="Override ALERT_EMAIL_TO for this run")
    parser.add_argument("--timeout", type=float, default=10.0, help="HTTP timeout seconds")
    parser.add_argument("--no-email", action="store_true", help="Don't send; just print")
    parser.add_argument("--no-insights", action="store_true", help="Skip the Insights section")
    parser.add_argument("--no-ai", action="store_true", help="Skip the AI Analysis section")
    args = parser.parse_args()

    banner("Agentic Monitor — Status Digest Demo")
    info(f"Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    info(f"Target URL: {args.url}")

    result = step1_fetch(args.url, timeout=args.timeout)
    ai_html, ai_text = ("", [])
    if result.get("ok") and not args.no_ai:
        ai_html, ai_text = _ai_analyze(
            result.get("payload"), args.url,
            result.get("status_code"), result.get("elapsed_ms"),
        )

    if not result.get("ok"):
        subject, html_body, text_body = step2_build_email(
            result, args.url, include_insights=not args.no_insights,
            ai_html=ai_html, ai_text=ai_text,
        )
        step3_send(subject, html_body, text_body, args.to, do_send=not args.no_email)
        sys.exit(2)

    subject, html_body, text_body = step2_build_email(
        result, args.url, include_insights=not args.no_insights,
        ai_html=ai_html, ai_text=ai_text,
    )
    ok(f"Email subject: \"{subject}\"")
    sent = step3_send(subject, html_body, text_body, args.to, do_send=not args.no_email)

    print()
    print(f"   📧 Recipient: {args.to or '(ALERT_EMAIL_TO from .env)'}")
    print(f"   📄 Payload size: {len(json.dumps(result['payload']))} chars (formatted JSON)")
    sys.exit(0 if sent else 1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(1)
