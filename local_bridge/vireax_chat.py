"""VIREAX multi-model chat for the local MirrorME bridge.

Routes a task through two or more models using VIREAX's bounded review
(``qviraex.vireax.multi_model.converse``). Models are either local Ollama models
or cloud models (Anthropic, OpenAI, Google Gemini) from a catalog the operator
configures when starting the bridge.

Trust boundaries:
- The browser chooses model identifiers, never endpoints or credentials.
- Cloud endpoints are fixed below; API keys are read from the bridge's own
  environment and are never returned to the browser.
- A request that includes any cloud model must carry ``allow_cloud: true``,
  the operator's explicit consent to send the task to that provider.
- Results are always ``completed_unverified``: model agreement is not verification.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from qviraex.vireax.adapters import AdapterSpec  # noqa: E402
from qviraex.vireax.anthropic_adapter import ANTHROPIC_MESSAGES_ENDPOINT, AnthropicAdapter  # noqa: E402
from qviraex.vireax.multi_model import CRITIC_LENSES, converse  # noqa: E402
from qviraex.vireax.openai_compatible_adapter import OpenAICompatibleAdapter  # noqa: E402
from qviraex.vireax.router import ModelRouter  # noqa: E402
from qviraex.vireax.system_prompt import load_vireax_system_prompt  # noqa: E402

MAX_TASK_CHARS = 20_000
MAX_OUTPUT_CHARS = 8_000
MAX_CHAT_MODELS = 4
DEFAULT_ROUNDS = 2
MODEL_CALL_TIMEOUT_SECONDS = 120.0
CLOUD_MAX_OUTPUT_TOKENS = 2_048
_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


@dataclass(frozen=True)
class CloudProvider:
    key: str
    label: str
    kind: str  # "anthropic" or "openai" (OpenAI-compatible chat completions)
    endpoint: str
    key_env: str
    max_tokens_field: str = "max_tokens"


CLOUD_PROVIDERS: dict[str, CloudProvider] = {
    "anthropic": CloudProvider(
        "anthropic", "Anthropic", "anthropic", ANTHROPIC_MESSAGES_ENDPOINT, "ANTHROPIC_API_KEY",
    ),
    "openai": CloudProvider(
        "openai", "OpenAI", "openai", "https://api.openai.com/v1/chat/completions",
        "OPENAI_API_KEY", max_tokens_field="max_completion_tokens",
    ),
    "gemini": CloudProvider(
        "gemini", "Google Gemini", "openai",
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions", "GEMINI_API_KEY",
    ),
}
# Offered automatically when the provider's key is set and the operator lists no
# models for it. Other providers' model IDs change often, so they are opt-in.
DEFAULT_CLOUD_MODELS: dict[str, tuple[str, ...]] = {
    "anthropic": ("claude-sonnet-5-5", "claude-haiku-5-5"),
}


@dataclass(frozen=True)
class CloudModel:
    id: str  # "provider/api-model", what the browser sends
    provider: CloudProvider
    api_model: str

    def available(self, environ: Mapping[str, str]) -> bool:
        return bool(environ.get(self.provider.key_env))


class VireaxRequestError(ValueError):
    """The browser sent an invalid VIREAX chat request (HTTP 400)."""


class VireaxModelError(RuntimeError):
    """A model call failed (HTTP 502)."""


def build_cloud_catalog(
    entries: Sequence[str],
    environ: Mapping[str, str] | None = None,
) -> dict[str, CloudModel]:
    """Build the operator's cloud catalog from ``provider/model`` entries.

    Raises ValueError for an unknown provider or malformed entry, so a typo stops
    the bridge at start-up instead of failing silently later.
    """
    env = os.environ if environ is None else environ
    catalog: dict[str, CloudModel] = {}
    listed: set[str] = set()
    for entry in entries:
        provider_key, sep, api_model = entry.strip().partition("/")
        if not sep or not api_model or provider_key not in CLOUD_PROVIDERS:
            raise ValueError(
                f"cloud model must be provider/model with provider one of "
                f"{', '.join(CLOUD_PROVIDERS)}: {entry!r}"
            )
        if not _MODEL_NAME.match(api_model):
            raise ValueError(f"invalid cloud model name: {entry!r}")
        listed.add(provider_key)
        model_id = f"{provider_key}/{api_model}"
        catalog[model_id] = CloudModel(model_id, CLOUD_PROVIDERS[provider_key], api_model)
    for provider_key, models in DEFAULT_CLOUD_MODELS.items():
        provider = CLOUD_PROVIDERS[provider_key]
        if provider_key in listed or not env.get(provider.key_env):
            continue
        for api_model in models:
            model_id = f"{provider_key}/{api_model}"
            catalog[model_id] = CloudModel(model_id, provider, api_model)
    return catalog


def _validate_models(raw: Any, fallback: Sequence[str]) -> list[str]:
    models = raw if raw is not None else list(fallback)
    if not isinstance(models, list) or not all(isinstance(m, str) for m in models):
        raise VireaxRequestError("models must be a list of model names")
    models = [m.strip() for m in models]
    if len(models) < 2:
        raise VireaxRequestError("choose at least two models")
    if len(models) > MAX_CHAT_MODELS:
        raise VireaxRequestError(f"choose at most {MAX_CHAT_MODELS} models")
    if len(set(models)) != len(models):
        raise VireaxRequestError("models must be different")
    for name in models:
        if not _MODEL_NAME.match(name):
            raise VireaxRequestError(f"invalid model name: {name[:40]!r}")
    return models


def _make_adapter(name: str, cloud: CloudModel | None, ollama_url: str, system_prompt: str) -> Any:
    if cloud is None:
        return OpenAICompatibleAdapter(
            AdapterSpec(model=name, provider="ollama", role="analyst"),
            endpoint=ollama_url.rstrip("/") + "/v1/chat/completions",
            api_model=name,
            timeout_seconds=MODEL_CALL_TIMEOUT_SECONDS,
            system_prompt=system_prompt,
        )
    spec = AdapterSpec(model=name, provider=cloud.provider.key, role="analyst")
    if cloud.provider.kind == "anthropic":
        return AnthropicAdapter(
            spec,
            api_model=cloud.api_model,
            api_key_env=cloud.provider.key_env,
            endpoint=cloud.provider.endpoint,
            max_output_tokens=CLOUD_MAX_OUTPUT_TOKENS,
            timeout_seconds=MODEL_CALL_TIMEOUT_SECONDS,
            system_prompt=system_prompt,
        )
    return OpenAICompatibleAdapter(
        spec,
        endpoint=cloud.provider.endpoint,
        api_model=cloud.api_model,
        api_key_env=cloud.provider.key_env,
        timeout_seconds=MODEL_CALL_TIMEOUT_SECONDS,
        max_output_tokens=CLOUD_MAX_OUTPUT_TOKENS,
        max_tokens_field=cloud.provider.max_tokens_field,
        system_prompt=system_prompt,
    )


def run_vireax_chat(
    payload: dict[str, Any],
    *,
    ollama_url: str,
    default_models: Sequence[str] = (),
    cloud_catalog: Mapping[str, CloudModel] | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """Run one bounded VIREAX conversation and return a JSON-safe result."""
    env = os.environ if environ is None else environ
    catalog = cloud_catalog or {}
    if not isinstance(payload, dict):
        raise VireaxRequestError("request body must be a JSON object")
    task = payload.get("task")
    if not isinstance(task, str) or not task.strip():
        raise VireaxRequestError("task must be a non-empty string")
    if len(task) > MAX_TASK_CHARS:
        raise VireaxRequestError(f"task is longer than {MAX_TASK_CHARS:,} characters")
    rounds = payload.get("max_rounds", DEFAULT_ROUNDS)
    if not isinstance(rounds, int) or isinstance(rounds, bool) or not 1 <= rounds <= 3:
        raise VireaxRequestError("max_rounds must be 1, 2 or 3")
    models = _validate_models(payload.get("models"), default_models)
    lenses = payload.get("critic_lenses")
    if lenses is not None:
        if not isinstance(lenses, list) or not lenses or not all(isinstance(x, str) for x in lenses):
            raise VireaxRequestError("critic_lenses must be a non-empty list")
        if any(x not in CRITIC_LENSES for x in lenses) or len(set(lenses)) != len(lenses):
            raise VireaxRequestError("critic_lenses must be distinct values from: " + ", ".join(CRITIC_LENSES))
        if rounds < 2:
            raise VireaxRequestError("critics need at least 2 rounds")
    synthesis = payload.get("synthesis", False)
    if not isinstance(synthesis, bool):
        raise VireaxRequestError("synthesis must be true or false")
    synthesis_model = None
    if synthesis:
        requested = payload.get("synthesis_model")
        if requested is None:
            synthesis_model = models[0]
        elif isinstance(requested, str) and requested in models:
            synthesis_model = requested
        else:
            raise VireaxRequestError("synthesis_model must be one of the selected models")

    cloud_selected = [catalog[m] for m in models if m in catalog]
    if cloud_selected:
        if payload.get("allow_cloud") is not True:
            providers = sorted({c.provider.label for c in cloud_selected})
            raise VireaxRequestError(
                "cloud_consent_required: confirm sending this task to " + ", ".join(providers)
            )
        missing = sorted({c.provider.key_env for c in cloud_selected if not c.available(env)})
        if missing:
            raise VireaxRequestError("API key not set on the bridge: " + ", ".join(missing))

    prompt = load_vireax_system_prompt()
    router = ModelRouter()
    for name in models:
        router.register(_make_adapter(name, catalog.get(name), ollama_url, prompt.text))
    local_models = [m for m in models if m not in catalog]
    details = ollama_model_details(ollama_url, local_models) if len(local_models) >= 2 else {}

    try:
        result = converse(
            router,
            task=task,
            model_names=models,
            max_rounds=rounds,
            max_output_chars=MAX_OUTPUT_CHARS,
            max_task_chars=MAX_TASK_CHARS,
            critic_lenses=lenses,
            synthesis_model=synthesis_model,
        )
    except (RuntimeError, ValueError) as exc:
        # Adapter errors are written to be safe to show (no secrets or bodies).
        raise VireaxModelError(str(exc)) from None

    providers = {name: (catalog[name].provider.key if name in catalog else "ollama") for name in models}
    return {
        "ok": True,
        "session_id": result.session_id,
        "task_id": result.task_id,
        "status": result.status,
        "models": models,
        "providers": providers,
        "sent_to_cloud": sorted({c.provider.label for c in cloud_selected}),
        "max_rounds": rounds,
        "critic_lenses": lenses or [],
        "synthesis_model": synthesis_model,
        "model_calls": len(models) * rounds + (1 if synthesis_model else 0),
        "system_prompt": {"version": prompt.version, "sha256": prompt.sha256},
        "independence": independence_report(models, catalog, details),
        "audit_head_hash": result.audit.head_hash,
        "turns": [
            {
                "round": turn.round_number,
                "model": turn.model,
                "provider": providers.get(turn.model, "ollama"),
                "role": turn.role,
                "output": turn.output,
                "output_sha256": turn.output_sha256,
            }
            for turn in result.turns
        ],
    }


def list_ollama_models(ollama_url: str, timeout_seconds: float = 5.0) -> list[str]:
    """Return the model names installed in the local Ollama runtime."""
    request = urllib.request.Request(ollama_url.rstrip("/") + "/api/tags", method="GET")
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        data = json.loads(response.read(1_000_000).decode("utf-8"))
    names = [m.get("name") for m in data.get("models", []) if isinstance(m, dict)]
    return sorted(n for n in names if isinstance(n, str) and _MODEL_NAME.match(n))


def describe_cloud_catalog(
    catalog: Mapping[str, CloudModel],
    environ: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    """Browser-safe view of the cloud catalog: never includes keys or endpoints."""
    env = os.environ if environ is None else environ
    return [
        {
            "id": model.id,
            "provider": model.provider.key,
            "provider_label": model.provider.label,
            "available": model.available(env),
            "key_env": model.provider.key_env,
        }
        for model in sorted(catalog.values(), key=lambda m: m.id)
    ]


def ollama_model_details(
    ollama_url: str,
    names: Sequence[str],
    timeout_seconds: float = 5.0,
) -> dict[str, dict[str, str]]:
    """Base-model facts from Ollama's /api/show; missing entries mean unknown."""
    details: dict[str, dict[str, str]] = {}
    for name in names:
        request = urllib.request.Request(
            ollama_url.rstrip("/") + "/api/show",
            data=json.dumps({"model": name}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                data = json.loads(response.read(2_000_000).decode("utf-8"))
        except (OSError, ValueError):
            continue
        info = data.get("details") if isinstance(data, dict) else None
        if not isinstance(info, dict):
            continue
        details[name] = {
            key: str(info.get(field) or "")
            for key, field in (
                ("family", "family"),
                ("parameter_size", "parameter_size"),
                ("quantization", "quantization_level"),
                ("parent_model", "parent_model"),
            )
        }
    return details


def _base_signature(info: Mapping[str, str]) -> str | None:
    if info.get("parent_model"):
        return "parent:" + info["parent_model"]
    if info.get("family") and info.get("parameter_size"):
        return "|".join((info["family"], info["parameter_size"], info.get("quantization", "")))
    return None


def independence_report(
    models: Sequence[str],
    catalog: Mapping[str, CloudModel],
    details: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    """Disclose selections that are unlikely to be independent.

    Local models with the same family, size and quantization (or parent model) are
    almost certainly one base model with different settings. This is a heuristic
    from Ollama metadata, so it is labelled "likely", and distinct models can still
    share training data and errors.
    """
    groups: dict[str, list[str]] = {}
    for name in models:
        if name in catalog:
            continue
        signature = _base_signature(details.get(name, {}))
        if signature:
            groups.setdefault(signature, []).append(name)
    shared = [names for names in groups.values() if len(names) > 1]
    notes = [
        f"{', '.join(names)} are likely the same base model with different settings; "
        "their agreement is not independent."
        for names in shared
    ]
    providers = [catalog[m].provider.key if m in catalog else "ollama" for m in models]
    if len(models) >= 2 and len(set(providers)) == 1 and not shared:
        notes.append("All selected models come from one provider; their errors may be correlated.")
    return {"same_base_groups": shared, "notes": notes}
