import logging
import time
import os
import json
from typing import Union
from config.settings import settings

logger = logging.getLogger(__name__)


def _build_prompt(event: Union[dict, object], rag_context: str) -> str:
    event_data = {}
    if isinstance(event, dict):
        event_data = event
    else:
        # try to extract fields from ORM object
        event_data = {
            "source_type": getattr(event, "source_type", ""),
            "source_name": getattr(event, "source_name", ""),
            "metric_name": getattr(event, "metric_name", ""),
            "metric_value": getattr(event, "metric_value", ""),
            "raw_data": getattr(event, "raw_data", {}),
        }

    return f"""
You are an IT operations monitoring agent. Generate a concise alert.

Event: {event_data}
Runbook context: {rag_context}

Write an alert with:
1. One sentence summary of what is wrong
2. The metric value and why it is concerning
3. Immediate recommended action from the runbook
4. Severity level

Keep under 150 words. Write for an IT operations analyst.
"""


def _call_anthropic(prompt: str, max_retries: int = 3) -> str:
    try:
        from anthropic import Client as AnthropicClient
    except Exception:
        raise

    api_key = settings.ANTHROPIC_API_KEY
    client = AnthropicClient(api_key)
    backoff = 1
    for attempt in range(max_retries):
        try:
            resp = client.completions.create(model="claude-2", prompt=prompt, max_tokens_to_sample=300)
            return resp.get("completion") or getattr(resp, "completion", str(resp))
        except Exception as e:
            logger.warning("Anthropic call failed (attempt %d): %s", attempt + 1, e)
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError("Anthropic API failed after retries")


def _call_openai(prompt: str, max_retries: int = 3) -> str:
    try:
        import openai
    except Exception:
        raise

    openai.api_key = settings.OPENAI_API_KEY
    backoff = 1
    for attempt in range(max_retries):
        try:
            resp = openai.ChatCompletion.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
            )
            return resp["choices"][0]["message"]["content"]
        except Exception as e:
            logger.warning("OpenAI call failed (attempt %d): %s", attempt + 1, e)
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError("OpenAI API failed after retries")


def _call_minimax(prompt: str, max_retries: int = 3) -> str:
    """Call the MinMax 3.0 API for alert generation."""
    if not settings.MINIMAX_API_KEY or not settings.MINIMAX_API_BASE_URL:
        raise RuntimeError("MinMax API key or base URL not configured")

    base_url = settings.MINIMAX_API_BASE_URL.rstrip("/")
    endpoint = base_url if base_url.endswith("/chat/completions") else f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": settings.MINIMAX_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }

    backoff = 1
    last_exception = None
    for attempt in range(max_retries):
        try:
            import requests
            response = requests.post(endpoint, headers=headers, json=payload, timeout=20)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, dict):
                choices = data.get("choices") or []
                if choices:
                    choice = choices[0]
                    if isinstance(choice, dict):
                        message = choice.get("message") or {}
                        if isinstance(message, dict):
                            content = message.get("content")
                            if isinstance(content, list):
                                return "".join(part.get("text", "") if isinstance(part, dict) else str(part) for part in content)
                            if isinstance(content, str):
                                return content
                        if isinstance(choice.get("text"), str):
                            return choice.get("text")
                if isinstance(data.get("message"), str):
                    return data.get("message")
                if isinstance(data.get("text"), str):
                    return data.get("text")
                if isinstance(data.get("response"), str):
                    return data.get("response")
            return json.dumps(data)
        except Exception as e:
            last_exception = e
            logger.warning("MinMax API call failed (attempt %d): %s", attempt + 1, e)
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError("MinMax API failed after retries") from last_exception


def _call_ollama(prompt: str, max_retries: int = 3) -> str:
    """Generate text from a local Ollama model via its HTTP API.

    Uses /api/generate with stream=False, which returns a single JSON object
    containing a `response` field. This avoids depending on any particular
    version of the `ollama` python client.
    """
    import requests

    url = settings.OLLAMA_BASE_URL.rstrip("/") + "/api/generate"
    payload = {"model": settings.LLM_MODEL, "prompt": prompt, "stream": False}
    backoff = 1
    last_exception = None
    for attempt in range(max_retries):
        try:
            r = requests.post(url, json=payload, timeout=120)
            r.raise_for_status()
            data = r.json()
            if isinstance(data, dict):
                text = data.get("response")
                if isinstance(text, str) and text.strip():
                    return text
            return str(data)
        except Exception as e:
            last_exception = e
            logger.warning("Ollama call failed (attempt %d): %s", attempt + 1, e)
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError("Ollama API failed after retries") from last_exception


def generate_alert_text(event: Union[dict, object], rag_context: str) -> str:
    """Generate an alert text using the selected LLM provider. Falls back to a plain alert on failure."""
    prompt = _build_prompt(event, rag_context)
    fallback = _fallback_for_event(event)
    text = generate_text(prompt, fallback=fallback)
    return (text or fallback).strip()


def _fallback_for_event(event) -> str:
    if isinstance(event, dict):
        ev = event
    else:
        ev = {
            "source": getattr(event, "source_name", ""),
            "metric": getattr(event, "metric_name", ""),
            "value": getattr(event, "metric_value", ""),
        }
    return f"ALERT: {ev.get('metric') or ev.get('metric_name')}={ev.get('value')} from {ev.get('source')}. (Details unavailable)"


def generate_text(prompt: str, fallback: str = "") -> str:
    """Run an arbitrary prompt through the configured LLM provider.

    Returns `fallback` (or empty string) if the provider is unreachable so
    callers can keep working when the LLM is down.
    """
    provider = settings.LLM_PROVIDER.lower() if settings.LLM_PROVIDER else "anthropic"
    try:
        if provider == "openai":
            text = _call_openai(prompt)
        elif provider in {"ollama", "local"}:
            text = _call_ollama(prompt)
        elif provider == "minmax":
            text = _call_minimax(prompt)
        else:
            text = _call_anthropic(prompt)
        return str(text).strip()
    except Exception:
        logger.exception("LLM provider failed")
        return ""
