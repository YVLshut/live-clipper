"""Appel réel du SDK Anthropic avec un transport HTTP simulé (aucun appel réseau)."""
from __future__ import annotations

import json

import anthropic
import httpx2
import pytest

from liveclipper.pipeline import highlights

CFG = {"ai_model": "claude-sonnet-5-5"}


def _client(handler):
    return anthropic.Anthropic(api_key="sk-test", max_retries=0,
                               http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def test_ask_claude_parses_structured_output():
    seen = {}

    def handler(request: httpx2.Request):
        body = json.loads(request.content)
        seen["body"], seen["headers"] = body, request.headers
        payload = {"clips": [{"start": "00:01:00", "end": "00:01:30", "score": 9, "title": "T",
                              "hook": "H", "caption": "C", "hashtags": ["#a"]}]}
        return httpx2.Response(200, json={
            "id": "msg_1", "type": "message", "role": "assistant", "model": body["model"],
            "content": [{"type": "text", "text": json.dumps(payload)}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10}})

    res = highlights.ask_claude("transcription", CFG, "sk-test", client=_client(handler))
    assert res[0]["score"] == 9 and res[0]["hashtags"] == ["#a"]
    assert seen["body"]["model"] == "claude-sonnet-5-5"
    assert seen["body"]["output_config"]["format"]["type"] == "json_schema"
    assert seen["body"]["fallbacks"] == "default"
    assert "server-side-fallback-2026-07-01" in seen["headers"]["anthropic-beta"]


def test_ask_claude_bad_key_message():
    def handler(request):
        return httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error",
                                                                     "message": "invalid x-api-key"}})

    with pytest.raises(highlights.AIError, match="Clé API Anthropic invalide"):
        highlights.ask_claude("x", CFG, "sk-bad", client=_client(handler))
