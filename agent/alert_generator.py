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


def _call_local_llm(prompt: str, max_retries: int = 3) -> str:
    """Call a local Ollama-compatible model such as MinMax 3.0."""
    backoff = 1
    last_exception = None
    for attempt in range(max_retries):
        try:
            try:
                from ollama import Ollama
                client = Ollama(base_url=settings.OLLAMA_BASE_URL)
                if hasattr(client, "generate"):
                    resp = client.generate(model=settings.LLM_MODEL, prompt=prompt)
                elif hasattr(client, "create"):
                    resp = client.create(model=settings.LLM_MODEL, prompt=prompt)
                else:
                    raise RuntimeError("Unsupported Ollama client API")

                if isinstance(resp, dict):
                    return resp.get("content") or json.dumps(resp)
                return getattr(resp, "content", str(resp))
            except Exception:
                import requests
                url = settings.OLLAMA_BASE_URL.rstrip("/") + "/api/generate"
                payload = {"model": settings.LLM_MODEL, "prompt": prompt}
                r = requests.post(url, json=payload, timeout=10)
                r.raise_for_status()
                return r.text
        except Exception as e:
            last_exception = e
            logger.warning("Local LLM call failed (attempt %d): %s", attempt + 1, e)
            time.sleep(backoff)
            backoff *= 2
    raise RuntimeError("Local LLM provider failed after retries") from last_exception


def generate_alert_text(event: Union[dict, object], rag_context: str) -> str:
    """Generate an alert text using the selected LLM provider. Falls back to a plain alert on failure."""
    prompt = _build_prompt(event, rag_context)
    provider = settings.LLM_PROVIDER.lower() if settings.LLM_PROVIDER else "anthropic"
    try:
        if provider == "openai":
            text = _call_openai(prompt)
        elif provider in {"ollama", "minmax", "local"}:
            text = _call_local_llm(prompt)
        else:
            text = _call_anthropic(prompt)
        return str(text).strip()
    except Exception:
        logger.exception("LLM provider failed; returning fallback alert")
        if isinstance(event, dict):
            ev = event
        else:
            ev = {
                "source": getattr(event, "source_name", ""),
                "metric": getattr(event, "metric_name", ""),
                "value": getattr(event, "metric_value", ""),
            }
        return f"ALERT: {ev.get('metric') or ev.get('metric_name')}={ev.get('value')} from {ev.get('source')}. (Details unavailable)"
