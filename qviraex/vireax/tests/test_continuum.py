from __future__ import annotations

import unittest
from dataclasses import replace

from qviraex.vireax.consciousness_mode import EpistemicClass
from qviraex.vireax.continuum import ContinuumLedger


def digest(char: str) -> str:
    return "sha256:" + char * 64


class ContinuumLedgerTests(unittest.TestCase):
    def test_appends_linked_states_and_verifies_chain(self) -> None:
        ledger = ContinuumLedger(max_entries=8)
        first = ledger.append(
            event_id="e1", source="sensor", content="raw observation",
            epistemic_class=EpistemicClass.OBSERVATION, confidence=0.8,
            state_before_hash=None, state_after_hash=digest("a"),
            observed_at="2026-10-26T02:00:00Z",
        )
        second = ledger.append(
            event_id="e2", source="estimator", content="estimated state",
            epistemic_class=EpistemicClass.INFERENCE, confidence=0.6,
            state_before_hash=first.state_after_hash, state_after_hash=digest("b"),
            observed_at="2026-10-26T02:00:01+00:00",
        )
        self.assertEqual(second.previous_entry_hash, first.entry_hash)
        self.assertTrue(ledger.verify())
        self.assertEqual(ledger.continuity_report()["epistemic_classes"], ["observation", "inference"])

    def test_rejects_state_discontinuity(self) -> None:
        ledger = ContinuumLedger()
        ledger.append(
            event_id="e1", source="sensor", content="one",
            epistemic_class=EpistemicClass.OBSERVATION, confidence=1.0,
            state_before_hash=None, state_after_hash=digest("a"),
        )
        with self.assertRaisesRegex(ValueError, "previous state_after_hash"):
            ledger.append(
                event_id="e2", source="sensor", content="two",
                epistemic_class=EpistemicClass.OBSERVATION, confidence=1.0,
                state_before_hash=digest("c"), state_after_hash=digest("b"),
            )

    def test_rejects_duplicate_event_id_and_capacity_overflow(self) -> None:
        ledger = ContinuumLedger(max_entries=1)
        ledger.append(
            event_id="e1", source="sensor", content="one",
            epistemic_class=EpistemicClass.OBSERVATION, confidence=1.0,
            state_before_hash=None, state_after_hash=digest("a"),
        )
        with self.assertRaisesRegex(ValueError, "duplicate event_id"):
            ledger.append(
                event_id="e1", source="sensor", content="repeat",
                epistemic_class=EpistemicClass.OBSERVATION, confidence=1.0,
                state_before_hash=digest("a"), state_after_hash=digest("b"),
            )
        with self.assertRaises(OverflowError):
            ledger.append(
                event_id="e2", source="sensor", content="two",
                epistemic_class=EpistemicClass.OBSERVATION, confidence=1.0,
                state_before_hash=digest("a"), state_after_hash=digest("b"),
            )

    def test_detects_mutated_entry(self) -> None:
        ledger = ContinuumLedger()
        entry = ledger.append(
            event_id="e1", source="sensor", content="one",
            epistemic_class=EpistemicClass.OBSERVATION, confidence=1.0,
            state_before_hash=None, state_after_hash=digest("a"),
        )
        ledger._entries[0] = replace(entry, confidence=0.1)
        self.assertFalse(ledger.verify())

    def test_validates_confidence_and_timezone(self) -> None:
        ledger = ContinuumLedger()
        with self.assertRaises(ValueError):
            ledger.append(
                event_id="e1", source="sensor", content="one",
                epistemic_class=EpistemicClass.OBSERVATION, confidence=1.5,
                state_before_hash=None, state_after_hash=digest("a"),
            )
        with self.assertRaisesRegex(ValueError, "explicit timezone"):
            ledger.append(
                event_id="e1", source="sensor", content="one",
                epistemic_class=EpistemicClass.OBSERVATION, confidence=0.5,
                state_before_hash=None, state_after_hash=digest("a"),
                observed_at="2026-10-26T02:00:00",
            )

    def test_does_not_retain_raw_content(self) -> None:
        ledger = ContinuumLedger()
        ledger.append(
            event_id="e1", source="sensor", content="private raw content",
            epistemic_class=EpistemicClass.OBSERVATION, confidence=0.9,
            state_before_hash=None, state_after_hash=digest("a"),
        )
        self.assertNotIn("private raw content", repr(ledger.entries[0]))
        self.assertNotIn("private raw content", str(ledger.continuity_report()))


if __name__ == "__main__":
    unittest.main()
