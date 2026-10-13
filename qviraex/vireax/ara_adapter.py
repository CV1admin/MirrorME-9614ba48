"""Environment-configured adapter factory for the ARA (Dane Model) agent.

This module deliberately does not infer an API endpoint or model ID from a GitHub
profile. ARA must expose an OpenAI-compatible chat-completions endpoint configured
in the trusted local runtime.
"""
from __future__ import annotations

import os
from collections.abc import Mapping
from urllib.parse import urlparse

from .adapters import AdapterSpec
from .openai_compatible_adapter import OpenAICompatibleAdapter
from .router import ModelRouter


def create_ara_adapter_from_env(
    environ: Mapping[str, str] | None = None,
) -> OpenAICompatibleAdapter:
    """Build ARA adapter from explicit local environment configuration.

    Required:
      VIREAX_ARA_ENDPOINT: exact OpenAI-compatible /chat/completions URL
      VIREAX_ARA_MODEL: provider's exact model identifier

    For non-loopback HTTPS endpoints, configure VIREAX_ARA_API_KEY_ENV to name
    an environment variable containing the secret. Local loopback endpoints may
    be unauthenticated. Credentials and endpoint values must never come from
    untrusted chat input.
    """
    env = os.environ if environ is None else environ
    endpoint = env.get("VIREAX_ARA_ENDPOINT", "").strip()
    api_model = env.get("VIREAX_ARA_MODEL", "").strip()
    if not endpoint:
        raise RuntimeError("VIREAX_ARA_ENDPOINT must be configured in the trusted runtime")
    if not api_model:
        raise RuntimeError("VIREAX_ARA_MODEL must be configured in the trusted runtime")

    parsed = urlparse(endpoint)
    hostname = (parsed.hostname or "").lower()
    if hostname in {"github.com", "www.github.com"}:
        raise ValueError(
            "VIREAX_ARA_ENDPOINT is a GitHub webpage, not a model inference endpoint"
        )
    if not parsed.path.rstrip("/").endswith("/chat/completions") or parsed.query:
        raise ValueError(
            "VIREAX_ARA_ENDPOINT must be the exact OpenAI-compatible /chat/completions URL"
        )

    loopback_http = (
        parsed.scheme == "http"
        and hostname in {"localhost", "127.0.0.1", "::1"}
    )
    api_key_env = env.get("VIREAX_ARA_API_KEY_ENV", "").strip() or None
    if not loopback_http:
        if parsed.scheme != "https":
            raise ValueError("remote ARA endpoints must use HTTPS")
        if not api_key_env:
            raise RuntimeError(
                "remote ARA endpoint requires VIREAX_ARA_API_KEY_ENV to name a secret variable"
            )
        if not env.get(api_key_env):
            raise RuntimeError(
                f"remote ARA credential variable named by VIREAX_ARA_API_KEY_ENV is missing: {api_key_env}"
            )

    return OpenAICompatibleAdapter(
        AdapterSpec(model="ARA", provider="Dane Model", role="independent_analyst"),
        endpoint=endpoint,
        api_model=api_model,
        api_key_env=api_key_env,
    )


def register_ara_adapter(
    router: ModelRouter,
    environ: Mapping[str, str] | None = None,
) -> OpenAICompatibleAdapter:
    """Create and register ARA in a router; does not make a network request."""
    adapter = create_ara_adapter_from_env(environ)
    router.register(adapter)
    return adapter
