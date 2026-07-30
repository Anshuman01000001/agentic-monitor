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

    def test_extract_json_from_ndjson_stream(self):
        s = '{"model":"phi3","response":"{\\"classification\\":\\"critical\\",\\"confidence\\":0.95,\\"reason\\":\\"cpu high\\"}"}\n{"model":"phi3","response":"\n"}'
        parsed = classifier._extract_json_from_text(s)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("classification"), "critical")

    def test_extract_json_from_code_fenced_response(self):
        s = '```json\n{"classification": "warning", "confidence": 0.6, "reason": "latency"}\n```'
        parsed = classifier._extract_json_from_text(s)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("classification"), "warning")

    def test_extract_json_from_nested_response_field(self):
        s = '{"model":"phi3","response":"{\\"classification\\":\\"critical\\",\\"confidence\\":0.95,\\"reason\\":\\"cpu high\\"}"}'
        parsed = classifier._extract_json_from_text(s)
        self.assertIsInstance(parsed, dict)
        self.assertEqual(parsed.get("classification"), "critical")


if __name__ == "__main__":
    unittest.main()
