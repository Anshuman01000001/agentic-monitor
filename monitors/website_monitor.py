import ssl
import socket
import asyncio
from typing import Dict, Any
import httpx


async def check_website(target: str, timeout: int = 10) -> Dict[str, Any]:
    """Probe a website endpoint.

    `target` may be either a bare domain ("example.com") or a full URL
    ("https://example.com/api/status"). For SSL checks we always resolve
    the hostname regardless of which form was supplied.
    """
    from urllib.parse import urlparse

    result: Dict[str, Any] = {"target": target}
    if "://" in target:
        url = target
        parsed = urlparse(target)
        domain = parsed.hostname or target
    else:
        url = f"https://{target}"
        domain = target
    result["domain"] = domain
    result["url"] = url

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url, follow_redirects=True)
            result["status_code"] = r.status_code
            result["response_time_ms"] = int(r.elapsed.total_seconds() * 1000)
            result["reachable"] = True
    except Exception as e:
        result["status_code"] = None
        result["response_time_ms"] = None
        result["reachable"] = False
        result["error"] = str(e)

    # SSL expiry check (skipped for non-https URLs)
    if url.startswith("https://"):
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((domain, 443), timeout=5) as sock:
                with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert()
                    # cert['notAfter'] example: 'Jun 30 12:00:00 2026 GMT'
                    from datetime import datetime

                    notAfter = cert.get("notAfter")
                    if notAfter:
                        exp = datetime.strptime(notAfter, "%b %d %H:%M:%S %Y %Z")
                        delta = exp - datetime.utcnow()
                        result["ssl_days_remaining"] = delta.days
        except Exception:
            result.setdefault("ssl_days_remaining", None)

    return result
