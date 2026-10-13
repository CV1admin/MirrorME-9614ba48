"""VIREAX multi-model chat for the local MirrorME bridge.

Routes a task through two or more local Ollama models using VIREAX's bounded
review (``qviraex.vireax.multi_model.converse``). Every model call goes to the
bridge's configured Ollama URL; the browser can choose model names but never
the endpoint. Results are always ``completed_unverified``: model agreement is
not verification.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any, Sequence

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from qviraex.vireax.adapters import AdapterSpec  # noqa: E402
from qviraex.vireax.multi_model import converse  # noqa: E402
from qviraex.vireax.openai_compatible_adapter import OpenAICompatibleAdapter  # noqa: E402
from qviraex.vireax.router import ModelRouter  # noqa: E402

MAX_TASK_CHARS = 20_000
MAX_OUTPUT_CHARS = 8_000
MAX_CHAT_MODELS = 4
DEFAULT_ROUNDS = 2
MODEL_CALL_TIMEOUT_SECONDS = 120.0
_MODEL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$")


class VireaxRequestError(ValueError):
    """The browser sent an invalid VIREAX chat request (HTTP 400)."""


class VireaxModelError(RuntimeError):
    """A local model call failed (HTTP 502)."""


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


def run_vireax_chat(
    payload: dict[str, Any],
    *,
    ollama_url: str,
    default_models: Sequence[str] = (),
) -> dict[str, Any]:
    """Run one bounded VIREAX conversation and return a JSON-safe result."""
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

    endpoint = ollama_url.rstrip("/") + "/v1/chat/completions"
    router = ModelRouter()
    for name in models:
        router.register(
            OpenAICompatibleAdapter(
                AdapterSpec(model=name, provider="ollama", role="analyst"),
                endpoint=endpoint,
                api_model=name,
                timeout_seconds=MODEL_CALL_TIMEOUT_SECONDS,
            )
        )

    try:
        result = converse(
            router,
            task=task,
            model_names=models,
            max_rounds=rounds,
            max_output_chars=MAX_OUTPUT_CHARS,
            max_task_chars=MAX_TASK_CHARS,
        )
    except (RuntimeError, ValueError) as exc:
        # Adapter errors are written to be safe to show (no secrets or bodies).
        raise VireaxModelError(str(exc)) from None

    return {
        "ok": True,
        "session_id": result.session_id,
        "task_id": result.task_id,
        "status": result.status,
        "models": models,
        "max_rounds": rounds,
        "audit_head_hash": result.audit.head_hash,
        "turns": [
            {
                "round": turn.round_number,
                "model": turn.model,
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
