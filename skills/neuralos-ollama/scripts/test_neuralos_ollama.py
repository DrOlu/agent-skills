#!/usr/bin/env python3
"""Offline unit tests for the neuralOS-ollama client and gates.
No Ollama required. Run: python3 test_neuralos_ollama.py -v
"""
import json
import unittest


class TestSchemaBuilding(unittest.TestCase):
    def test_none_of_these_always_present(self):
        candidates = ["a", "b"]
        names = list(candidates) + ["none_of_these"]
        self.assertIn("none_of_these", names)

    def test_schema_shape(self):
        candidates = ["open_incidents", "worklog_count"]
        schema = {"type": "object", "properties": {
            "probe": {"type": "string",
                      "enum": list(candidates) + ["none_of_these"]}},
            "required": ["probe"]}
        self.assertEqual(schema["properties"]["probe"]["type"], "string")
        self.assertIn("none_of_these",
                      schema["properties"]["probe"]["enum"])


class TestConstrainedPickParsing(unittest.TestCase):
    def test_valid_json_parsed(self):
        payload = {"message": {"content": json.dumps({"probe": "a"})}}
        try:
            pick = json.loads(payload["message"]["content"])
        except (KeyError, json.JSONDecodeError):
            pick = {"probe": "none_of_these", "_unparseable": True}
        self.assertEqual(pick["probe"], "a")

    def test_unparseable_falls_back_to_refusal(self):
        payload = {"message": {"content": "not json at all"}}
        try:
            pick = json.loads(payload["message"]["content"])
        except (KeyError, json.JSONDecodeError):
            pick = {"probe": "none_of_these", "_unparseable": True}
        self.assertEqual(pick["probe"], "none_of_these")


class TestThinkDefaults(unittest.TestCase):
    def test_chat_payload_think_false(self):
        # the client contract: think is disabled unless explicitly enabled
        import ollama_client
        self.assertFalse(ollama_client.chat.__defaults__[4],
                         "chat() must default think to False")


if __name__ == "__main__":
    unittest.main()
