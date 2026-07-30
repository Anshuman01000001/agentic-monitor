import logging
import json
import re
import asyncio
from typing import Union
from config.settings import settings
# Import database modules lazily inside functions to avoid heavy imports during tests

logger = logging.getLogger(__name__)


async def _call_ollama_prompt(prompt: str) -> str:
    """Try to use the ollama Python client if available, otherwise fall back to HTTP request."""
    try:
        from ollama import Ollama

        client = Ollama(base_url=settings.OLLAMA_BASE_URL)
        # many Ollama clients provide a `generate` or `create` API; try common names
        if hasattr(client, "generate"):
            resp = client.generate(model=settings.SLM_MODEL, prompt=prompt)
            # resp may be a dict or have a 'content' attribute
            if isinstance(resp, dict):
                return resp.get("content") or json.dumps(resp)
            return getattr(resp, "content", str(resp))
        elif hasattr(client, "create"):
            resp = client.create(model=settings.SLM_MODEL, prompt=prompt)
            return getattr(resp, "content", str(resp))
    except Exception:
        logger.debug("ollama python client unavailable or failed, falling back to HTTP", exc_info=True)

    # fallback: call Ollama HTTP API
    try:
        import requests

        url = settings.OLLAMA_BASE_URL.rstrip("/") + "/api/generate"
        payload = {"model": settings.SLM_MODEL, "prompt": prompt, "stream": False}
        r = requests.post(url, json=payload, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception:
        logger.exception("Failed to contact Ollama via HTTP")
        raise


def _extract_json_from_text(text: str) -> Union[dict, None]:
    if not text:
        return None

    def _try_parse(candidate: str):
        if not candidate:
            return None
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            pass

        try:
            candidate = candidate.strip()
            if candidate.startswith("```"):
                candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
                candidate = re.sub(r"\s*```$", "", candidate)
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(candidate[start : end + 1])
        except Exception:
            return None
        return None

    parsed = _try_parse(text)
    if parsed and parsed.get("classification") is not None:
        return parsed

    if isinstance(parsed, dict):
        for key in ("response", "content", "message"):
            if isinstance(parsed.get(key), str):
                nested = _try_parse(parsed[key])
                if nested and nested.get("classification") is not None:
                    return nested

    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        parsed = _try_parse(fenced.group(1))
        if parsed:
            return parsed

    # Ollama may return newline-delimited JSON objects with a `response` field.
    response_parts = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except Exception:
            continue
        if isinstance(payload, dict):
            response = payload.get("response")
            if isinstance(response, str):
                response_parts.append(response)

    if response_parts:
        assembled = "".join(response_parts)
        parsed = _try_parse(assembled)
        if parsed:
            return parsed

    # Try to recover a JSON payload embedded inside a larger response string.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return _try_parse(text[start : end + 1])

    return None


async def classify_event_with_ollama(event: Union[dict, object]) -> dict:
    """Classify an event using Ollama SLM.

    Returns a dict: {classification, confidence, reason}.
    Also writes `classification`, `confidence`, and `reason` back to the Event DB record when an Event instance is supplied.
    """
    logger.debug("classify_event_with_ollama called for %s", getattr(event, "id", "<dict>"))

    # Normalize fields
    source_type = getattr(event, "source_type", None) or (event.get("source_type") if isinstance(event, dict) else None)
    source_name = getattr(event, "source_name", None) or (event.get("source_name") if isinstance(event, dict) else None)
    metric_name = getattr(event, "metric_name", None) or (event.get("metric_name") if isinstance(event, dict) else None)
    metric_value = getattr(event, "metric_value", None) or (event.get("metric_value") if isinstance(event, dict) else None)

    prompt = f"""
You are a system monitoring agent. Classify the following telemetry event.

Event:
- Source: {source_type} ({source_name})
- Metric: {metric_name}
- Value: {metric_value}

Respond in JSON only, no other text:
{{"classification": "normal|warning|critical", "confidence": 0.0-1.0, "reason": "one sentence"}}
"""
    try:
        text = await _call_ollama_prompt(prompt)
    except Exception:
        logger.exception("Ollama unreachable; skipping classification")
        return {"classification": "normal", "confidence": 0.0, "reason": "ollama unreachable"}

    parsed = _extract_json_from_text(text)
    if not parsed:
        logger.warning("Could not parse Ollama output; defaulting to normal. raw=%s", text)
        parsed = {"classification": "normal", "confidence": 0.0, "reason": "malformed model output"}

    classification = parsed.get("classification", "normal")
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except Exception:
        confidence = 0.0
    reason = parsed.get("reason", "") or ""

    # Persist back to DB if Event instance
    if hasattr(event, "id"):
        try:
            from database import db
            from database.models import Event as EventModel
        except Exception:
            logger.debug("Database modules unavailable; skipping DB write")
            session = None
        else:
            session = db.get_session()
        try:
            ev = session.get(EventModel, event.id)
            if ev:
                ev.classification = classification
                ev.confidence = confidence
                # Event model may have 'reason' column; set if exists
                if hasattr(ev, "reason"):
                    ev.reason = reason
                session.add(ev)
                session.commit()
        except Exception:
            if session:
                session.rollback()
            logger.exception("Failed to write classification to DB for event %s", getattr(event, "id", None))
        finally:
            if session:
                session.close()

    return {"classification": classification, "confidence": confidence, "reason": reason}
