import pytest

from qviraex.vireax.audit import AuditLedger
from qviraex.vireax.center_node import VIREAXCenterNode
from qviraex.vireax.gem_integration import ProtectedMemoryGradient, project_protected_update


def memory(memory_id="m1", status="supported", approved=True, gradient=(1.0, 0.0)):
    return ProtectedMemoryGradient(memory_id, gradient, status, approved)


def test_only_approved_evidence_qualified_memories_are_protected():
    result = project_protected_update([-1.0, 2.0], [memory()])
    assert result.converged
    assert result.gradient == pytest.approx((0.0, 2.0))


@pytest.mark.parametrize("status", ["hypothesis", "speculation", "unknown", "refuted"])
def test_unqualified_memory_cannot_become_constraint(status):
    with pytest.raises(ValueError, match="memory protection requires"):
        project_protected_update([-1.0, 2.0], [memory(status=status)])


def test_unapproved_memory_cannot_become_constraint():
    with pytest.raises(ValueError, match="memory protection requires"):
        project_protected_update([-1.0, 2.0], [memory(approved=False)])


def test_center_node_integration_audits_projection_without_gradient_values():
    ledger = AuditLedger()
    node = VIREAXCenterNode(router=None, audit_ledger=ledger)
    result = node.project_learning_update(
        session_id="session-test",
        operator="test-operator",
        candidate_gradient=[-1.0, 2.0],
        protected_memories=[memory()],
    )
    assert result.gradient == pytest.approx((0.0, 2.0))
    assert len(ledger.records) == 1
    record_text = str(ledger.records[0].payload)
    assert "m1" in record_text
    assert "-1.0" not in record_text


def test_center_node_audits_rejected_memory_protection():
    ledger = AuditLedger()
    node = VIREAXCenterNode(router=None, audit_ledger=ledger)
    with pytest.raises(ValueError, match="memory protection requires"):
        node.project_learning_update(
            session_id="session-test",
            operator="test-operator",
            candidate_gradient=[-1.0, 2.0],
            protected_memories=[memory(status="refuted")],
        )
    assert ledger.records[0].payload["decision"] == "GEM_PROJECTION_REJECTED"
