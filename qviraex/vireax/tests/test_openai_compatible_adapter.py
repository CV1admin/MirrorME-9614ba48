from __future__ import annotations

import json
import os
import unittest

from qviraex.vireax.adapters import AdapterEnvelope, AdapterSpec
from qviraex.vireax.openai_compatible_adapter import OpenAICompatibleAdapter


class FakeResponse:
    def __init__(self, body: bytes) -> None:
        self.body = body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        return self.body[:size]


class FakeOpener:
    def __init__(self, body: bytes) -> None:
        self.body = body
        self.request = None
        self.timeout = None

    def open(self, request: object, timeout: float) -> FakeResponse:
        self.request = request
        self.timeout = timeout
        return FakeResponse(self.body)


class OpenAICompatibleAdapterTests(unittest.TestCase):
    def make_adapter(self, endpoint: str = "https://models.example/v1/chat/completions") -> OpenAICompatibleAdapter:
        return OpenAICompatibleAdapter(
            AdapterSpec("ara", "test-provider", "critic"),
            endpoint=endpoint,
            api_model="dane-model",
            timeout_seconds=3,
        )

    def test_requires_https_unless_loopback(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            self.make_adapter("http://models.example/v1/chat/completions")
        self.assertIsNotNone(self.make_adapter("http://127.0.0.1:8000/v1/chat/completions"))

    def test_rejects_credentials_embedded_in_endpoint(self) -> None:
        with self.assertRaisesRegex(ValueError, "embedded credentials"):
            self.make_adapter("https://user:password@models.example/v1/chat/completions")

    def test_parses_openai_compatible_response_and_labels_confidence_unavailable(self) -> None:
        adapter = self.make_adapter()
        opener = FakeOpener(json.dumps({
            "id": "resp-test",
            "choices": [{"message": {"content": "I disagree; this claim needs evidence."}}],
        }).encode())
        adapter._opener = opener  # type: ignore[assignment]
        result = adapter.respond(AdapterEnvelope("ara", "critic", "Review this claim."))
        self.assertEqual(result.output, "I disagree; this claim needs evidence.")
        self.assertEqual(result.model, "ara")
        self.assertEqual(result.confidence, 0.0)
        self.assertFalse(result.metadata["confidence_is_calibrated"])
        self.assertEqual(opener.timeout, 3)
        sent = json.loads(opener.request.data.decode())  # type: ignore[union-attr]
        self.assertEqual(sent["model"], "dane-model")

    def test_missing_secret_fails_before_network_request(self) -> None:
        adapter = OpenAICompatibleAdapter(
            AdapterSpec("ara", "test-provider", "critic"),
            endpoint="https://models.example/v1/chat/completions",
            api_model="dane-model",
            api_key_env="VIREAX_TEST_MISSING_SECRET",
        )
        adapter._opener = FakeOpener(b"{}")  # type: ignore[assignment]
        os.environ.pop("VIREAX_TEST_MISSING_SECRET", None)
        with self.assertRaisesRegex(RuntimeError, "credential environment variable is missing"):
            adapter.respond(AdapterEnvelope("ara", "critic", "test"))

    def test_malformed_provider_response_is_rejected(self) -> None:
        adapter = self.make_adapter()
        adapter._opener = FakeOpener(b'{"choices": []}')  # type: ignore[assignment]
        with self.assertRaisesRegex(ValueError, "expected chat-completions schema"):
            adapter.respond(AdapterEnvelope("ara", "critic", "test"))

    def test_rejects_mismatched_target(self) -> None:
        adapter = self.make_adapter()
        with self.assertRaisesRegex(ValueError, "target does not match"):
            adapter.respond(AdapterEnvelope("different-model", "critic", "test"))


if __name__ == "__main__":
    unittest.main()
