"""Anthropic Messages API adapter using the Python standard library.

Mirrors the safety rules of ``OpenAICompatibleAdapter``: the endpoint and the name
of the credential variable come from trusted configuration, HTTPS is required
except on loopback, redirects are refused, and response size is bounded. Provider
error bodies are never surfaced, because they may echo request headers.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

from .adapters import AdapterEnvelope, AdapterResult, AdapterSpec
from .openai_compatible_adapter import DEFAULT_SYSTEM_PROMPT, _NoRedirectHandler

ANTHROPIC_MESSAGES_ENDPOINT = "https://api.anthropic.com/v1/messages"
ANTHROPIC_API_VERSION = "2023-06-01"
SYSTEM_PROMPT = DEFAULT_SYSTEM_PROMPT


class AnthropicAdapter:
    """Adapter for POST /v1/messages."""

    def __init__(
        self,
        spec: AdapterSpec,
        *,
        api_model: str,
        api_key_env: str = "ANTHROPIC_API_KEY",
        endpoint: str = ANTHROPIC_MESSAGES_ENDPOINT,
        max_output_tokens: int = 2_048,
        timeout_seconds: float = 60.0,
        max_response_bytes: int = 1_000_000,
        max_prompt_chars: int = 100_000,
        system_prompt: str | None = None,
    ) -> None:
        parsed = urlparse(endpoint)
        local_http = parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
        if parsed.scheme != "https" and not local_http:
            raise ValueError("endpoint must use HTTPS, except for explicit loopback HTTP")
        if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
            raise ValueError("endpoint URL is invalid or contains embedded credentials")
        if not api_model.strip():
            raise ValueError("api_model must be non-empty")
        if not api_key_env.strip():
            raise ValueError("api_key_env must name an environment variable")
        if not 1 <= max_output_tokens <= 32_000:
            raise ValueError("max_output_tokens must be between 1 and 32,000")
        if not 0 < timeout_seconds <= 300:
            raise ValueError("timeout_seconds must be in (0, 300]")
        if not 1 <= max_response_bytes <= 10_000_000:
            raise ValueError("max_response_bytes must be between 1 and 10,000,000")
        if not 1 <= max_prompt_chars <= 1_000_000:
            raise ValueError("max_prompt_chars must be between 1 and 1,000,000")
        if system_prompt is not None and not system_prompt.strip():
            raise ValueError("system_prompt must be non-empty when supplied")
        if not spec.enabled:
            raise ValueError("cannot initialize a disabled model adapter")

        self.spec = spec
        self.endpoint = endpoint
        self.api_model = api_model
        self.api_key_env = api_key_env
        self.max_output_tokens = max_output_tokens
        self.timeout_seconds = timeout_seconds
        self.max_response_bytes = max_response_bytes
        self.max_prompt_chars = max_prompt_chars
        self.system_prompt = system_prompt or SYSTEM_PROMPT
        self._opener = urllib.request.build_opener(_NoRedirectHandler())

    def respond(self, envelope: AdapterEnvelope) -> AdapterResult:
        if envelope.target_model != self.spec.model:
            raise ValueError("request target does not match adapter identity")
        if len(envelope.prompt) > self.max_prompt_chars:
            raise ValueError("prompt exceeds configured size limit")
        secret = os.environ.get(self.api_key_env)
        if not secret:
            raise RuntimeError(f"required credential environment variable is missing: {self.api_key_env}")

        payload = {
            "model": self.api_model,
            "max_tokens": self.max_output_tokens,
            "system": self.system_prompt,
            "messages": [{"role": "user", "content": envelope.prompt}],
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "x-api-key": secret,
                "anthropic-version": ANTHROPIC_API_VERSION,
            },
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                raw = response.read(self.max_response_bytes + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308):
                raise RuntimeError("provider redirects are disabled for credential safety") from None
            raise RuntimeError(f"provider returned HTTP {exc.code}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"provider request failed: {type(exc).__name__}") from None

        if len(raw) > self.max_response_bytes:
            raise RuntimeError("provider response exceeds configured size limit")
        try:
            data: dict[str, Any] = json.loads(raw.decode("utf-8"))
            blocks = data["content"]
            output = "".join(
                block["text"] for block in blocks
                if isinstance(block, dict) and block.get("type") == "text"
            )
        except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
            raise ValueError("provider response does not match the expected messages schema") from exc
        if not isinstance(output, str) or not output.strip():
            raise ValueError("provider returned empty or non-text message content")

        return AdapterResult(
            model=self.spec.model,
            provider=self.spec.provider,
            role=envelope.role,
            output=output,
            confidence=0.0,
            metadata={
                "api_model": self.api_model,
                "confidence_is_calibrated": False,
                "provider_response_id": data.get("id"),
                "stop_reason": data.get("stop_reason"),
            },
        )
