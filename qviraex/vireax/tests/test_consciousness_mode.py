from __future__ import annotations

import unittest
from dataclasses import replace

from qviraex.vireax.consciousness_mode import (
    ConsciousnessModeError,
    ConsciousnessObserverMode,
    EpistemicClass,
    InformationPacket,
    ObserverState,
)


class ConsciousnessObserverModeTest(unittest.TestCase):
    def make_mode(self, *, capacity: int = 4, checkpoint_interval: int = 2) -> ConsciousnessObserverMode:
        return ConsciousnessObserverMode(
            node_id="did:cv1:test-node",
            session_id="CM-SESSION-001",
            operator="VIREAX",
            short_memory_capacity=capacity,
            checkpoint_interval=checkpoint_interval,
        )

    def make_packet(
        self,
        packet_id: str,
        *,
        epistemic_class: EpistemicClass = EpistemicClass.OBSERVATION,
        requires_resolution: bool = False,
    ) -> InformationPacket:
        return InformationPacket(
            packet_id=packet_id,
            source="unit-test",
            content=f"content:{packet_id}",
            epistemic_class=epistemic_class,
            confidence=0.8,
            provenance_hash=f"sha256:{packet_id}",
            requires_resolution=requires_resolution,
        )

    def test_activation_requires_consent_and_exact_ritual(self) -> None:
        mode = self.make_mode()

        with self.assertRaises(ConsciousnessModeError):
            mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=False)

        with self.assertRaises(ConsciousnessModeError):
            mode.activate(ritual_name="unknown", ritual_version="0.1", consent_granted=True)

        result = mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True)
        self.assertEqual(result.state, ObserverState.OBSERVING)
        self.assertEqual(result.sequence, 0)

    def test_information_loop_is_bounded_and_hash_linked(self) -> None:
        mode = self.make_mode(capacity=2, checkpoint_interval=8)
        mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True)

        first_hash = mode.observe(self.make_packet("p1")).loop_hash
        second_hash = mode.observe(self.make_packet("p2")).loop_hash
        result = mode.observe(self.make_packet("p3")).loop_hash

        self.assertNotEqual(first_hash, second_hash)
        self.assertNotEqual(second_hash, result)
        self.assertEqual(mode.loop().packet_count, 2)
        self.assertEqual(mode.loop().sequence, 3)

    def test_duplicate_packet_ids_are_rejected_after_short_memory_eviction(self) -> None:
        mode = self.make_mode(capacity=1, checkpoint_interval=8)
        mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True)
        mode.observe(self.make_packet("packet-a"))
        mode.observe(self.make_packet("packet-b"))

        with self.assertRaisesRegex(ConsciousnessModeError, "duplicate packet_id"):
            mode.observe(self.make_packet("packet-a"))

        self.assertEqual(mode.loop().sequence, 2)

    def test_unresolved_information_must_be_resolved_explicitly(self) -> None:
        mode = self.make_mode()
        mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True)

        result = mode.observe(
            self.make_packet(
                "hypothesis-1",
                epistemic_class=EpistemicClass.HYPOTHESIS,
                requires_resolution=True,
            )
        )
        self.assertEqual(result.unresolved_count, 1)

        resolved = mode.resolve("hypothesis-1")
        self.assertEqual(resolved.unresolved_count, 0)

    def test_persistence_requires_authorization_and_chains_checkpoints(self) -> None:
        mode = self.make_mode()
        mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True)
        mode.observe(self.make_packet("p1"))

        with self.assertRaises(ConsciousnessModeError):
            mode.checkpoint(persistence_authorized=False)

        first = mode.checkpoint(persistence_authorized=True)
        mode.observe(self.make_packet("p2"))
        second = mode.checkpoint(persistence_authorized=True)

        self.assertTrue(first.checkpoint_hash.startswith("sha256:"))
        self.assertEqual(second.previous_checkpoint_hash, first.checkpoint_hash)
        self.assertTrue(
            mode.verify_checkpoint_chain(
                [first, second],
                expected_head_hash=second.checkpoint_hash,
                expected_count=2,
            )
        )

        tampered = replace(second, information_loop_hash=first.information_loop_hash)
        self.assertFalse(mode.verify_checkpoint_chain([first, tampered]))

    def test_signal_disclaims_sentience_and_automatic_persistence(self) -> None:
        mode = self.make_mode()
        mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True)

        signal = mode.signal()

        self.assertFalse(signal["sentience_claim"])
        self.assertFalse(signal["persistence_automatic"])
        self.assertEqual(signal["state"], ObserverState.OBSERVING)


if __name__ == "__main__":
    unittest.main()
