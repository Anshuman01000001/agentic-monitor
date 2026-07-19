from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pipeline.collector import get_recent_events
import os

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    html = """
    <html>
    <head>
        <title>Agentic Monitor</title>
        <style>
            body { font-family: sans-serif; margin: 20px; }
            h1 { color: #333; }
            table { border-collapse: collapse; width: 100%; margin-top: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
        </style>
    </head>
    <body>
        <h1>Agentic Monitor Dashboard</h1>
        <p><a href="/alerts">View Alert History</a></p>
        <h2>Recent Events</h2>
        <div id="events-container">Loading...</div>
        <script>
            fetch('/api/events?limit=20')
                .then(r => r.json())
                .then(events => {
                    if (!events || events.length === 0) {
                        document.getElementById('events-container').innerHTML = '<p>No events yet.</p>';
                        return;
                    }
                    let html = '<table><tr><th>Time</th><th>Source</th><th>Metric</th><th>Value</th><th>Class</th></tr>';
                    events.forEach(e => {
                        html += `<tr><td>${e.timestamp}</td><td>${e.source_type}/${e.source_name}</td><td>${e.metric_name}</td><td>${e.metric_value}</td><td>${e.classification || 'pending'}</td></tr>`;
                    });
                    html += '</table>';
                    document.getElementById('events-container').innerHTML = html;
                })
                .catch(err => {
                    document.getElementById('events-container').innerHTML = '<p>Error loading events: ' + err + '</p>';
                });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


@router.get("/alerts", response_class=HTMLResponse)
async def alerts(request: Request):
    html = "<html><body><h1>Alert History</h1><p>Placeholder for alert history table.</p></body></html>"
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
