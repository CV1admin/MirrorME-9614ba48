"""Audited VIREÁX integration boundary for GEM gradient projection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .gem_projection import ProjectionResult, Vector, project_gradient

_PROTECTABLE_STATUSES = frozenset({"established", "supported", "validated_invariant"})


@dataclass(frozen=True)
class ProtectedMemoryGradient:
    """Numerical gradient tied to a reviewed memory record.

    approved_for_protection is a policy decision supplied by a trusted caller;
    this data class does not independently authenticate that decision.
    """
    memory_id: str
    gradient: tuple[float, ...]
    evidence_status: str
    approved_for_protection: bool


def project_protected_update(
    candidate_gradient: Vector,
    protected_memories: Sequence[ProtectedMemoryGradient],
    *,
    tolerance: float = 1e-10,
    max_iterations: int = 10_000,
) -> ProjectionResult:
    """Project against approved, evidence-qualified memory gradients only.

    Provisional, speculative, unknown, refuted, or unapproved memories fail
    closed instead of silently becoming immutable constraints.
    """
    invalid = [
        memory.memory_id
        for memory in protected_memories
        if not memory.memory_id
        or not memory.approved_for_protection
        or memory.evidence_status not in _PROTECTABLE_STATUSES
    ]
    if invalid:
        raise ValueError(
            "memory protection requires a non-empty ID, explicit approval, "
            "and evidence_status in established/supported/validated_invariant; "
            f"rejected IDs: {invalid}"
        )

    return project_gradient(
        candidate_gradient,
        [memory.gradient for memory in protected_memories],
        tolerance=tolerance,
        max_iterations=max_iterations,
    )
