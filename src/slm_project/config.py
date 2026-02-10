from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings: 
    base_url: str = os.getenv("SLM_BASE_URL", "http://localhost:3000/v1")
    api_key: str = os.getenv("SLM_API_KEY", "notneeded")
    model: str = os.getenv("SLM_MODEL", "gpt-4-0613")
    temperature: float = float(os.getenv("SLM_TEMPERATURE", "0.7"))
    timeout_s: float = float(os.getenv("SLM_TIMEOUT_S", "60.0"))