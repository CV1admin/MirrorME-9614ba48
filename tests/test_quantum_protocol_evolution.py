from __future__ import annotations

import math
import unittest
from dataclasses import replace

from qviraex.quantum import (
    ObservableTerm,
    OptimizerSpec,
    QuantumIntegrationProtocol,
    QuantumProtocolError,
    QuantumRunRequest,
    bootstrap_mean_interval,
    coefficient_weighted_hoeffding,
    group_commuting_observables,
    normalize_observables,
    pauli_words_commute,
    wilson_interval,
)
from qviraex.quantum.providers import LocalDeterministicProvider
from qviraex.vireax.audit import AuditLedger


QASM3 = """OPENQASM 3.0;
bit[3] c;
qubit[3] q;
c[0] = measure q[0];
c[1] = measure q[1];
c[2] = measure q[2];
"""


class GovernedQuantumEvolutionTest(unittest.TestCase):
    def make_request(self) -> QuantumRunRequest:
        return QuantumRunRequest(
            session_id="VX-QIP-EVOLUTION-1",
            operator="VIREAX",
            circuit_qasm=QASM3,
            qubit_count=3,
            mode="variational",
            provider="local",
            backend_name="local-reference",
            shots=2048,
            parameters={f"theta{index}": 0.0 for index in range(6)},
            observables=(
                ObservableTerm("ZIX", 1.0),
                ObservableTerm("ZXI", -0.5),
                ObservableTerm("IXX", 0.5),
            ),
            optimizer=OptimizerSpec(initial_parameters=(0.0,) * 6),
            metadata={"source": "governed QIP evolution test"},
        )

    def test_duplicate_observables_are_aggregated_deterministically(self) -> None:
        first = normalize_observables(
            (
                ObservableTerm("zix", 0.25),
                ObservableTerm("IXX", 0.5),
                ObservableTerm("ZIX", 0.75),
            ),
            3,
        )
        second = normalize_observables(
            (
                ObservableTerm("ZIX", 0.75),
                ObservableTerm("ZIX", 0.25),
                ObservableTerm("IXX", 0.5),
            ),
            3,
        )
        self.assertEqual(first, second)
        self.assertEqual(
            first,
            (ObservableTerm("IXX", 0.5), ObservableTerm("ZIX", 1.0)),
        )

    def test_duplicate_reject_policy(self) -> None:
        request = replace(
            self.make_request(),
            observables=(ObservableTerm("ZII", 1.0), ObservableTerm("zii", 2.0)),
            duplicate_observable_policy="reject",
        )
        with self.assertRaisesRegex(QuantumProtocolError, "Duplicate observable"):
            request.validate()

    def test_commutation_grouping(self) -> None:
        self.assertTrue(pauli_words_commute("ZIX", "ZXI"))
        self.assertFalse(pauli_words_commute("ZII", "XII"))
        groups = group_commuting_observables(
            (
                ObservableTerm("ZII", 1.0),
                ObservableTerm("IZI", 1.0),
                ObservableTerm("XII", 1.0),
            ),
            3,
        )
        self.assertEqual(len(groups), 2)
        for group in groups:
            for index, term in enumerate(group):
                for other in group[index + 1 :]:
                    self.assertTrue(pauli_words_commute(term.pauli, other.pauli))

    def test_weighted_hoeffding_separates_empirical_variance(self) -> None:
        report = coefficient_weighted_hoeffding(
            (ObservableTerm("Z", 1.0), ObservableTerm("X", -0.5)),
            {"Z": 1000, "X": 500},
            confidence_level=0.95,
            empirical_variances={"Z": 0.36, "X": 0.64},
        )
        expected_proxy = 1.0 / 1000 + 0.25 / 500
        self.assertAlmostEqual(report.theoretical_variance_proxy, expected_proxy)
        self.assertAlmostEqual(
            report.half_width,
            math.sqrt(2.0 * expected_proxy * math.log(40.0)),
        )
        self.assertAlmostEqual(
            report.empirical_variance_of_estimator,
            0.36 / 1000 + 0.25 * 0.64 / 500,
        )
        self.assertIn("not a hardware-accuracy", report.interpretation)

    def test_wilson_and_bootstrap_intervals(self) -> None:
        lower, upper = wilson_interval(50, 100)
        self.assertLess(lower, 0.5)
        self.assertGreater(upper, 0.5)
        first = bootstrap_mean_interval(
            (-1.0, 1.0, 1.0, -1.0),
            resamples=400,
            seed=9,
        )
        second = bootstrap_mean_interval(
            (-1.0, 1.0, 1.0, -1.0),
            resamples=400,
            seed=9,
        )
        self.assertEqual(first, second)
        self.assertLessEqual(first[0], 0.0)
        self.assertGreaterEqual(first[1], 0.0)

    def test_audit_failure_does_not_invalidate_raw_receipt(self) -> None:
        ledger = AuditLedger()
        protocol = QuantumIntegrationProtocol(audit_ledger=ledger)
        receipt = protocol.execute(
            self.make_request(),
            LocalDeterministicProvider(results={"expectation_value": -2.0}),
        )
        self.assertTrue(protocol.verify_receipt(receipt))
        self.assertTrue(protocol.verify_audit_anchor(receipt))

        ledger._records[0] = replace(ledger._records[0], previous_hash="corrupt")
        self.assertFalse(protocol.verify_audit_anchor(receipt))
        self.assertTrue(protocol.verify_receipt(receipt))

    def test_missing_record_and_replay_handling(self) -> None:
        ledger = AuditLedger()
        protocol = QuantumIntegrationProtocol(audit_ledger=ledger)
        receipt = protocol.execute(
            self.make_request(),
            LocalDeterministicProvider(results={"expectation_value": -2.0}),
        )
        with self.assertRaisesRegex(QuantumProtocolError, "replayed"):
            protocol.anchor_receipt(replace(receipt, audit_anchor=None))

        ledger._records.clear()
        self.assertFalse(protocol.verify_audit_anchor(receipt))
        self.assertTrue(protocol.verify_receipt(receipt))

    def test_ledger_can_be_disabled(self) -> None:
        ledger = AuditLedger()
        protocol = QuantumIntegrationProtocol(
            audit_ledger=ledger,
            audit_anchoring_enabled=False,
        )
        receipt = protocol.execute(
            self.make_request(),
            LocalDeterministicProvider(results={"expectation_value": -2.0}),
        )
        self.assertIsNone(receipt.audit_anchor)
        self.assertEqual(ledger.records, [])
        self.assertTrue(protocol.verify_receipt(receipt))

    def test_mitigated_values_require_raw_values(self) -> None:
        with self.assertRaisesRegex(QuantumProtocolError, "corresponding raw"):
            QuantumIntegrationProtocol().execute(
                self.make_request(),
                LocalDeterministicProvider(results={"mitigated_expectation": -2.0}),
            )


if __name__ == "__main__":
    unittest.main()
