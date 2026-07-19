import unittest
from agent import alert_generator
from config import settings


class TestAlertGeneratorFallback(unittest.TestCase):
    def test_fallback_on_missing_llm(self):
        # force provider to openai and ensure keys are None to trigger fallback
        settings.LLM_PROVIDER = "openai"
        settings.OPENAI_API_KEY = None
        event = {"source_name": "testhost", "metric_name": "cpu", "metric_value": 99}
        text = alert_generator.generate_alert_text(event, "")
        self.assertIsInstance(text, str)
        self.assertTrue(text.startswith("ALERT:") or "Details unavailable" in text)


if __name__ == "__main__":
    unittest.main()
