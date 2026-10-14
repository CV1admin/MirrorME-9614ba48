from __future__ import annotations

import io
import json
import os
import unittest
import urllib.error
from unittest import mock

from qviraex.vireax.adapters import AdapterEnvelope, AdapterSpec
from qviraex.vireax.anthropic_adapter import ANTHROPIC_API_VERSION, AnthropicAdapter
from qviraex.vireax.openai_compatible_adapter import OpenAICompatibleAdapter


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body if size < 0 else self.body[:size]


class FakeOpener:
    def __init__(self, body: bytes = b"", error: Exception | None = None) -> None:
        self.body = body
        self.error = error
        self.request = None

    def open(self, request, timeout: float) -> FakeResponse:
        self.request = request
        if self.error:
            raise self.error
        return FakeResponse(self.body)


def envelope(target: str = "anthropic/claude-test") -> AdapterEnvelope:
    return AdapterEnvelope(target_model=target, role="independent_analyst", prompt="Assess the claim.")


class AnthropicAdapterTests(unittest.TestCase):
    def make(self, **kwargs) -> AnthropicAdapter:
        return AnthropicAdapter(
            AdapterSpec("anthropic/claude-test", "anthropic", "analyst"),
            api_model="claude-test",
            api_key_env="TEST_ANTHROPIC_KEY",
            **kwargs,
        )

    def test_sends_messages_request_with_key_version_and_token_cap(self) -> None:
        adapter = self.make(max_output_tokens=512)
        adapter._opener = FakeOpener(json.dumps({
            "id": "msg_1",
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": "Needs evidence. "}, {"type": "text", "text": "Unverified."}],
        }).encode())
        with mock.patch.dict(os.environ, {"TEST_ANTHROPIC_KEY": "sk-test"}):
            result = adapter.respond(envelope())
        request = adapter._opener.request
        self.assertEqual(request.full_url, "https://api.anthropic.com/v1/messages")
        self.assertEqual(request.get_header("X-api-key"), "sk-test")
        self.assertEqual(request.get_header("Anthropic-version"), ANTHROPIC_API_VERSION)
        body = json.loads(request.data)
        self.assertEqual(body["model"], "claude-test")
        self.assertEqual(body["max_tokens"], 512)
        self.assertIn("untrusted claims", body["system"])
        self.assertEqual(body["messages"], [{"role": "user", "content": "Assess the claim."}])
        self.assertEqual(result.output, "Needs evidence. Unverified.")
        self.assertEqual(result.model, "anthropic/claude-test")
        self.assertEqual(result.provider, "anthropic")
        self.assertEqual(result.role, "independent_analyst")
        self.assertFalse(result.metadata["confidence_is_calibrated"])

    def test_missing_key_fails_before_any_request(self) -> None:
        adapter = self.make()
        adapter._opener = FakeOpener()
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "TEST_ANTHROPIC_KEY"):
                adapter.respond(envelope())
        self.assertIsNone(adapter._opener.request)

    def test_http_error_does_not_leak_body_or_key(self) -> None:
        adapter = self.make()
        error = urllib.error.HTTPError(
            "https://api.anthropic.com/v1/messages", 401, "Unauthorized", {}, io.BytesIO(b"bad key sk-test"),
        )
        adapter._opener = FakeOpener(error=error)
        with mock.patch.dict(os.environ, {"TEST_ANTHROPIC_KEY": "sk-test"}):
            with self.assertRaises(RuntimeError) as ctx:
                adapter.respond(envelope())
        self.assertEqual(str(ctx.exception), "provider returned HTTP 401")

    def test_rejects_unexpected_schema_and_empty_text(self) -> None:
        for body in ({"choices": []}, {"content": [{"type": "tool_use", "id": "x"}]}):
            with self.subTest(body=body):
                adapter = self.make()
                adapter._opener = FakeOpener(json.dumps(body).encode())
                with mock.patch.dict(os.environ, {"TEST_ANTHROPIC_KEY": "sk-test"}):
                    with self.assertRaises(ValueError):
                        adapter.respond(envelope())

    def test_identity_mismatch_rejected(self) -> None:
        adapter = self.make()
        adapter._opener = FakeOpener()
        with self.assertRaisesRegex(ValueError, "adapter identity"):
            adapter.respond(envelope("someone-else"))

    def test_requires_https_unless_loopback(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            self.make(endpoint="http://api.example/v1/messages")
        self.assertIsNotNone(self.make(endpoint="http://127.0.0.1:9/v1/messages"))

    def test_custom_system_prompt_is_sent(self) -> None:
        adapter = self.make(system_prompt="You are VIREAX.")
        adapter._opener = FakeOpener(json.dumps({"content": [{"type": "text", "text": "ok"}]}).encode())
        with mock.patch.dict(os.environ, {"TEST_ANTHROPIC_KEY": "sk-test"}):
            adapter.respond(envelope())
        self.assertEqual(json.loads(adapter._opener.request.data)["system"], "You are VIREAX.")
        with self.assertRaisesRegex(ValueError, "system_prompt"):
            self.make(system_prompt="  ")

    def test_output_token_cap_is_bounded(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_output_tokens"):
            self.make(max_output_tokens=0)


class OpenAICompatibleTokenCapTests(unittest.TestCase):
    def test_token_cap_field_is_sent_only_when_configured(self) -> None:
        reply = json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode()
        for kwargs, field in (({}, None), ({"max_output_tokens": 256, "max_tokens_field": "max_completion_tokens"}, "max_completion_tokens")):
            with self.subTest(kwargs=kwargs):
                adapter = OpenAICompatibleAdapter(
                    AdapterSpec("m", "p", "r"), endpoint="https://models.example/v1/chat/completions",
                    api_model="m", **kwargs,
                )
                adapter._opener = FakeOpener(reply)
                adapter.respond(AdapterEnvelope(target_model="m", role="r", prompt="x"))
                body = json.loads(adapter._opener.request.data)
                if field is None:
                    self.assertNotIn("max_tokens", body)
                    self.assertNotIn("max_completion_tokens", body)
                else:
                    self.assertEqual(body[field], 256)

    def test_custom_system_prompt_is_sent(self) -> None:
        adapter = OpenAICompatibleAdapter(
            AdapterSpec("m", "p", "r"), endpoint="https://models.example/v1/chat/completions",
            api_model="m", system_prompt="You are VIREAX.",
        )
        adapter._opener = FakeOpener(json.dumps({"choices": [{"message": {"content": "ok"}}]}).encode())
        adapter.respond(AdapterEnvelope(target_model="m", role="r", prompt="x"))
        messages = json.loads(adapter._opener.request.data)["messages"]
        self.assertEqual(messages[0], {"role": "system", "content": "You are VIREAX."})

    def test_rejects_unknown_token_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "max_tokens_field"):
            OpenAICompatibleAdapter(
                AdapterSpec("m", "p", "r"), endpoint="https://models.example/v1/chat/completions",
                api_model="m", max_output_tokens=10, max_tokens_field="tokens",
            )


if __name__ == "__main__":
    unittest.main()
