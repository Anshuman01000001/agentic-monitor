import unittest
from agent import classifier


class TestClassifierUtils(unittest.TestCase):
    def test_extract_json_direct(self):
        s = '{"classification": "critical", "confidence": 0.9, "reason": "high cpu"}'
        parsed = classifier._extract_json_from_text(s)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("classification"), "critical")

    def test_extract_json_with_noise(self):
        s = 'Some preface text. {"classification": "warning", "confidence": 0.5, "reason": "latency"} some trailing.'
        parsed = classifier._extract_json_from_text(s)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("classification"), "warning")

    def test_extract_json_malformed(self):
        s = 'no json here'
        parsed = classifier._extract_json_from_text(s)
        self.assertIsNone(parsed)


if __name__ == "__main__":
    unittest.main()
