import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # dotenv not installed in test environments; ignore
    pass

class Settings:
    LLM_PROVIDER = os.getenv("LLM_PROVIDER", "anthropic")
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    SLM_MODEL = os.getenv("SLM_MODEL", os.getenv("OLLAMA_MODEL", "phi3"))
    LLM_MODEL = os.getenv("LLM_MODEL", "MinMax-3.0")

    SMTP_HOST = os.getenv("SMTP_HOST")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
    ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO")

    MONITOR_DOMAINS = [d.strip() for d in os.getenv("MONITOR_DOMAINS", "").split(",") if d.strip()]
    DEVICE_CHECK_INTERVAL = int(os.getenv("DEVICE_CHECK_INTERVAL", "60"))
    WEBSITE_CHECK_INTERVAL = int(os.getenv("WEBSITE_CHECK_INTERVAL", "300"))

    SLM_CRITICAL_CONFIDENCE_THRESHOLD = float(os.getenv("SLM_CRITICAL_CONFIDENCE_THRESHOLD", "0.75"))
    CONSECUTIVE_WARNINGS_BEFORE_ALERT = int(os.getenv("CONSECUTIVE_WARNINGS_BEFORE_ALERT", "3"))

    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./monitor.db")
    CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./chroma_store")


settings = Settings()
