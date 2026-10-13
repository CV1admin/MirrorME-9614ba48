from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from .adapters import AdapterEnvelope, AdapterResult, AdapterSpec, StaticAdapter


class ModelAdapter(Protocol):
    """Structural contract implemented by static, local, and remote adapters."""

    spec: AdapterSpec

    def respond(self, envelope: AdapterEnvelope) -> AdapterResult: ...


@dataclass
class ModelRouter:
    registry: dict[str, ModelAdapter] = field(default_factory=dict)

    def register(self, adapter: ModelAdapter) -> None:
        if not getattr(adapter, "spec", None) or not callable(getattr(adapter, "respond", None)):
            raise TypeError("adapter must expose spec and respond(envelope)")
        model_name = adapter.spec.model
        if not model_name or not adapter.spec.enabled:
            raise ValueError("adapter must have a model name and be enabled")
        self.registry[model_name] = adapter

    def dispatch(self, target_model: str, envelope: AdapterEnvelope) -> AdapterResult:
        if target_model not in self.registry:
            raise KeyError(f"adapter not registered: {target_model}")
        adapter = self.registry[target_model]
        result = adapter.respond(envelope)
        if not isinstance(result, AdapterResult):
            raise TypeError(f"adapter {target_model!r} returned an invalid result")
        if result.model != target_model:
            raise ValueError(f"adapter identity mismatch: expected {target_model!r}, got {result.model!r}")
        return result
