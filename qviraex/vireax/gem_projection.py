"""GEM-style gradient projection for VIREÁX's experimental learning layer.

This module is an optimisation primitive only. It does not determine whether a
memory is true or authoritative; callers must select protected gradients using
separate provenance, evidence, consent, and policy rules.

For protected loss gradients m_k, the feasible update satisfies
    dot(projected_gradient, m_k) >= 0
which prevents a first-order increase in each protected loss under gradient
descent. Finite-step non-regression must be checked separately.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Sequence

Vector = Sequence[float]


@dataclass(frozen=True)
class ProjectionResult:
    gradient: tuple[float, ...]
    changed: bool
    converged: bool
    iterations: int
    max_constraint_violation: float
    projection_distance: float
    retained_norm: float


def _dot(a: Vector, b: Vector) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: Vector) -> float:
    return sqrt(_dot(a, a))


def _sub(a: Vector, b: Vector) -> tuple[float, ...]:
    return tuple(x - y for x, y in zip(a, b))


def _add(a: Vector, b: Vector) -> tuple[float, ...]:
    return tuple(x + y for x, y in zip(a, b))


def _project_halfspace(v: Vector, normal: Vector) -> tuple[float, ...]:
    """Euclidean projection onto {x: dot(x, normal) >= 0}."""
    value = _dot(v, normal)
    if value >= 0:
        return tuple(v)
    norm_sq = _dot(normal, normal)
    if norm_sq == 0:
        return tuple(v)
    scale = value / norm_sq
    return tuple(x - scale * n for x, n in zip(v, normal))


def project_gradient(
    gradient: Vector,
    memory_gradients: Sequence[Vector],
    *,
    tolerance: float = 1e-10,
    max_iterations: int = 10_000,
) -> ProjectionResult:
    """Project a gradient onto all GEM half-space constraints.

    Uses Dykstra's algorithm to compute the nearest point in the intersection
    of the feasible half-spaces. For one constraint, this is the exact closed
    form. The function uses only the Python standard library.

    Zero memory gradients impose no constraint and are ignored. Invalid
    dimensions, non-finite values, and invalid solver settings raise ValueError.
    """
    if not gradient:
        raise ValueError("gradient must not be empty")
    if tolerance <= 0 or max_iterations < 1:
        raise ValueError("tolerance must be positive and max_iterations >= 1")

    g = tuple(float(x) for x in gradient)
    memories = [tuple(float(x) for x in m) for m in memory_gradients]
    if any(len(m) != len(g) for m in memories):
        raise ValueError("all memory gradients must match gradient dimension")
    if any(not all(__import__("math").isfinite(x) for x in v) for v in [g, *memories]):
        raise ValueError("gradient values must be finite")

    # A zero normal creates no meaningful inequality; omit it.
    normals = [m for m in memories if _dot(m, m) > 0]
    if not normals:
        return ProjectionResult(g, False, True, 0, 0.0, 0.0, _norm(g))

    # Dykstra correction vectors, one per half-space.
    x = g
    corrections = [tuple(0.0 for _ in g) for _ in normals]
    converged = False
    iterations = 0

    for iteration in range(1, max_iterations + 1):
        previous = x
        for i, normal in enumerate(normals):
            y = _add(x, corrections[i])
            projected = _project_halfspace(y, normal)
            corrections[i] = _sub(y, projected)
            x = projected
        iterations = iteration
        violation = max(0.0, max(-_dot(x, n) for n in normals))
        if _norm(_sub(x, previous)) <= tolerance and violation <= tolerance:
            converged = True
            break

    max_violation = max(0.0, max(-_dot(x, n) for n in normals))
    distance = _norm(_sub(x, g))
    return ProjectionResult(
        gradient=tuple(x),
        changed=distance > tolerance,
        converged=converged,
        iterations=iterations,
        max_constraint_violation=max_violation,
        projection_distance=distance,
        retained_norm=_norm(x),
    )
