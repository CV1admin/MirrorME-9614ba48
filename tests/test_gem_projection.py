import math

import pytest

from qviraex.vireax.gem_projection import project_gradient


def test_no_conflict_is_pass_through():
    result = project_gradient([1.0, 0.0], [[1.0, 0.0]])
    assert result.gradient == (1.0, 0.0)
    assert not result.changed
    assert result.converged


def test_orthogonal_gradient_is_pass_through():
    result = project_gradient([0.0, 1.0], [[1.0, 0.0]])
    assert result.gradient == (0.0, 1.0)
    assert not result.changed


def test_135_degree_collision_projects_to_boundary():
    # g=(cos 135°, sin 135°), memory=(1,0); projection removes x component.
    result = project_gradient([-1 / math.sqrt(2), 1 / math.sqrt(2)], [[1.0, 0.0]])
    assert result.converged
    assert result.gradient[0] == pytest.approx(0.0, abs=1e-9)
    assert result.gradient[1] == pytest.approx(1 / math.sqrt(2))
    assert result.max_constraint_violation <= 1e-9


def test_exact_opposition_projects_to_zero():
    result = project_gradient([-1.0, 0.0], [[1.0, 0.0]])
    assert result.gradient == pytest.approx((0.0, 0.0), abs=1e-9)
    assert result.retained_norm == pytest.approx(0.0, abs=1e-9)


def test_multiple_constraints_are_satisfied():
    result = project_gradient([-1.0, -2.0], [[1.0, 0.0], [0.0, 1.0]])
    assert result.converged
    assert result.gradient == pytest.approx((0.0, 0.0), abs=1e-9)
    assert result.max_constraint_violation <= 1e-9


def test_dimension_mismatch_is_rejected():
    with pytest.raises(ValueError, match="dimension"):
        project_gradient([1.0, 2.0], [[1.0]])


def test_zero_memory_gradient_is_ignored():
    result = project_gradient([1.0, -2.0], [[0.0, 0.0]])
    assert result.gradient == (1.0, -2.0)
    assert result.converged
