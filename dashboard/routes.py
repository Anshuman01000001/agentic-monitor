from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pipeline.collector import get_recent_events, get_recent_alerts

router = APIRouter()

_STYLE = """
<style>
    body { font-family: system-ui, sans-serif; margin: 24px; color: #1a1a1a; background: #fafafa; }
    h1 { color: #222; }
    nav a { margin-right: 16px; text-decoration: none; color: #0366d6; font-weight: 600; }
    table { border-collapse: collapse; width: 100%; margin-top: 16px; background: #fff; }
    th, td { border: 1px solid #e1e4e8; padding: 8px 10px; text-align: left; font-size: 14px; vertical-align: top; }
    th { background-color: #f2f4f6; }
    .normal { color: #22863a; }
    .warning { color: #b08800; font-weight: 600; }
    .critical { color: #d73a49; font-weight: 700; }
    .yes { color: #d73a49; font-weight: 600; }
    pre { white-space: pre-wrap; margin: 0; font-family: inherit; }
</style>
"""


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    html = f"""
    <html>
    <head><title>Agentic Monitor</title>{_STYLE}</head>
    <body>
        <h1>Agentic Monitor Dashboard</h1>
        <nav><a href="/">Events</a><a href="/alerts">Alert History</a></nav>
        <h2>Recent Events</h2>
        <div id="events-container">Loading...</div>
        <script>
            fetch('/api/events?limit=25')
                .then(r => r.json())
                .then(events => {{
                    if (!events || events.length === 0) {{
                        document.getElementById('events-container').innerHTML = '<p>No events yet.</p>';
                        return;
                    }}
                    let html = '<table><tr><th>Time</th><th>Source</th><th>Metric</th><th>Value</th><th>Class</th><th>Conf.</th><th>Escalated</th></tr>';
                    events.reverse().forEach(e => {{
                        const cls = (e.classification || 'pending');
                        const conf = (e.confidence != null) ? e.confidence.toFixed(2) : '';
                        html += `<tr><td>${{e.timestamp || ''}}</td><td>${{e.source_type}}/${{e.source_name}}</td><td>${{e.metric_name}}</td><td>${{e.metric_value}}</td><td class="${{cls}}">${{cls}}</td><td>${{conf}}</td><td class="${{e.escalated ? 'yes' : ''}}">${{e.escalated ? 'yes' : 'no'}}</td></tr>`;
                    }});
                    html += '</table>';
                    document.getElementById('events-container').innerHTML = html;
                }})
                .catch(err => {{
                    document.getElementById('events-container').innerHTML = '<p>Error loading events: ' + err + '</p>';
                }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/alerts", response_class=HTMLResponse)
async def alerts(request: Request):
    html = f"""
    <html>
    <head><title>Alert History</title>{_STYLE}</head>
    <body>
        <h1>Alert History</h1>
        <nav><a href="/">Events</a><a href="/alerts">Alert History</a></nav>
        <div id="alerts-container">Loading...</div>
        <script>
            fetch('/api/alerts?limit=50')
                .then(r => r.json())
                .then(alerts => {{
                    if (!alerts || alerts.length === 0) {{
                        document.getElementById('alerts-container').innerHTML = '<p>No alerts generated yet.</p>';
                        return;
                    }}
                    let html = '<table><tr><th>Time</th><th>Source</th><th>Metric</th><th>Alert</th><th>Emailed To</th><th>Sent At</th></tr>';
                    alerts.forEach(a => {{
                        html += `<tr><td>${{a.timestamp || ''}}</td><td>${{a.source_type || ''}}/${{a.source_name || ''}}</td><td>${{a.metric_name || ''}} = ${{a.metric_value != null ? a.metric_value : ''}}</td><td><pre>${{(a.alert_text || '').replace(/</g,'&lt;')}}</pre></td><td>${{a.email_sent_to || ''}}</td><td>${{a.email_sent_at || 'not sent'}}</td></tr>`;
                    }});
                    html += '</table>';
                    document.getElementById('alerts-container').innerHTML = html;
                }})
                .catch(err => {{
                    document.getElementById('alerts-container').innerHTML = '<p>Error loading alerts: ' + err + '</p>';
                }});
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/api/events")
async def api_events(limit: int = 50):
    """Fetch recent events as JSON."""
    try:
        events = get_recent_events(limit=limit)
        return JSONResponse([{
            "id": e.id,
            "timestamp": e.timestamp.isoformat() if e.timestamp else None,
            "source_type": e.source_type,
            "source_name": e.source_name,
            "metric_name": e.metric_name,
            "metric_value": e.metric_value,
            "classification": e.classification,
            "confidence": e.confidence,
            "escalated": e.escalated,
        } for e in events])
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/alerts")
async def api_alerts(limit: int = 50):
    """Fetch recent alerts (joined with their event) as JSON."""
    try:
        return JSONResponse(get_recent_alerts(limit=limit))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
