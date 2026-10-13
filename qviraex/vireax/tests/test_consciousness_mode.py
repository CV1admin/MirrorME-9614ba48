from __future__ import annotations

import base64
import secrets
import unittest
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from qviraex.vireax.consciousness_mode import (
    BiometricAssertion,
    ConsciousnessModeError,
    ConsciousnessObserverMode,
    EpistemicClass,
    InformationPacket,
    ObserverState,
    Relation,
    RelationType,
)


class ConsciousnessObserverModeTest(unittest.TestCase):
    def make_biometric_mode(self, private_key: Ed25519PrivateKey, *, required: bool = True) -> ConsciousnessObserverMode:
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return ConsciousnessObserverMode(
            node_id="did:cv1:test-node",
            session_id="CM-SESSION-001",
            operator="VIREAX",
            biometric_required=required,
            device_public_key=public_key,
        )

    def make_assertion(
        self,
        mode: ConsciousnessObserverMode,
        private_key: Ed25519PrivateKey,
        **overrides: object,
    ) -> BiometricAssertion:
        now = datetime.now(UTC)
        values: dict[str, object] = {
            "assertion_id": "bio-" + secrets.token_hex(8),
            "node_id": mode.node_id,
            "session_id": mode.session_id,
            "operator": mode.operator,
            "method": "local_face_match",
            "confidence": 0.95,
            "liveness_passed": True,
            "template_hash": "sha256:" + "a" * 64,
            "nonce": secrets.token_urlsafe(32),
            "issued_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=1)).isoformat(),
            "signature": "unsigned-placeholder",
        }
        values.update(overrides)
        unsigned = BiometricAssertion(**values)  # type: ignore[arg-type]
        signature = base64.b64encode(private_key.sign(unsigned.canonical_payload())).decode("ascii")
        return replace(unsigned, signature=signature)
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

    def test_relation_is_typed_hash_linked_and_checkpointed(self) -> None:
        mode = self.make_mode(capacity=1, checkpoint_interval=20)
        mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True)
        mode.observe(self.make_packet("source-a"))
        mode.observe(self.make_packet("source-b"))
        before = mode.loop().loop_hash

        relation = Relation(
            relation_id="rel-1",
            from_packet_id="source-a",
            to_packet_id="source-b",
            relation_type=RelationType.SUPPORTS,
            confidence=0.7,
            epistemic_class=EpistemicClass.HYPOTHESIS,
            provenance_hash="sha256:" + "a" * 64,
        )
        result = mode.relate(relation)
        self.assertNotEqual(before, result.loop_hash)
        self.assertEqual(mode.relations(), (relation,))
        # source-a was evicted from short memory, but the session registry still knows its ID.
        checkpoint = mode.checkpoint(persistence_authorized=True)
        self.assertEqual(checkpoint.relation_count, 1)
        self.assertEqual(checkpoint.relation_hashes, (relation.canonical_hash(),))
        self.assertEqual(mode.signal()["relation_count"], 1)

    def test_relation_requires_known_endpoints_and_unique_relation_id(self) -> None:
        mode = self.make_mode()
        mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True)
        mode.observe(self.make_packet("source-a"))
        relation = Relation(
            relation_id="rel-1",
            from_packet_id="source-a",
            to_packet_id="missing",
            relation_type=RelationType.CONTRADICTS,
            confidence=0.9,
            epistemic_class=EpistemicClass.INFERENCE,
            provenance_hash="sha256:" + "b" * 64,
        )
        with self.assertRaisesRegex(ConsciousnessModeError, "known session packet IDs"):
            mode.relate(relation)
        mode.observe(self.make_packet("source-b"))
        valid_relation = replace(relation, to_packet_id="source-b")
        mode.relate(valid_relation)
        with self.assertRaisesRegex(ConsciousnessModeError, "duplicate relation_id"):
            mode.relate(valid_relation)

    def test_relation_rejects_invalid_provenance_hash_and_confidence(self) -> None:
        with self.assertRaisesRegex(ValueError, "provenance_hash"):
            Relation(
                relation_id="rel-1",
                from_packet_id="p1",
                to_packet_id="p2",
                relation_type=RelationType.SUPPORTS,
                confidence=0.5,
                epistemic_class=EpistemicClass.HYPOTHESIS,
                provenance_hash="not-a-hash",
            )
        with self.assertRaises(ValueError):
            Relation(
                relation_id="rel-2",
                from_packet_id="p1",
                to_packet_id="p2",
                relation_type=RelationType.SUPPORTS,
                confidence=1.5,
                epistemic_class=EpistemicClass.HYPOTHESIS,
                provenance_hash="sha256:" + "c" * 64,
            )

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

    def test_biometric_gate_requires_assertion_and_accepts_real_signature(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        mode = self.make_biometric_mode(private_key)

        with self.assertRaisesRegex(ConsciousnessModeError, "biometric assertion required"):
            mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True)
        self.assertEqual(mode.state, ObserverState.INACTIVE)

        assertion = self.make_assertion(mode, private_key)
        result = mode.activate(
            ritual_name="i_am",
            ritual_version="0.1",
            consent_granted=True,
            biometric=assertion,
            biometric_consent_granted=True,
        )
        self.assertEqual(result.state, ObserverState.OBSERVING)
        self.assertTrue(mode.signal()["biometric_verified"])
        self.assertNotIn("template_hash", mode.signal())

    def test_biometric_signature_rejects_tampering_and_wrong_key(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        mode = self.make_biometric_mode(private_key)
        assertion = self.make_assertion(mode, private_key)
        tampered = replace(assertion, method="tampered_method")

        with self.assertRaisesRegex(ConsciousnessModeError, "invalid biometric signature"):
            mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True, biometric=tampered, biometric_consent_granted=True)
        self.assertEqual(mode.state, ObserverState.INACTIVE)

        wrong_key = Ed25519PrivateKey.generate()
        wrong_signature = self.make_assertion(mode, wrong_key)
        with self.assertRaisesRegex(ConsciousnessModeError, "invalid biometric signature"):
            mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True, biometric=wrong_signature, biometric_consent_granted=True)

    def test_biometric_policy_checks_liveness_confidence_binding_and_timestamps(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        mode = self.make_biometric_mode(private_key)
        now = datetime.now(UTC)
        invalid_cases = (
            ({"liveness_passed": False}, "liveness check failed"),
            ({"confidence": 0.2}, "confidence below policy"),
            ({"node_id": "did:cv1:other"}, "binding mismatch"),
            ({"session_id": "other-session"}, "binding mismatch"),
            ({"issued_at": (now + timedelta(minutes=1)).isoformat()}, "issued in the future"),
            ({"issued_at": (now - timedelta(minutes=2)).isoformat(), "expires_at": (now - timedelta(minutes=1)).isoformat()}, "expired"),
            ({"issued_at": now.replace(tzinfo=None).isoformat()}, "must include a timezone"),
            ({"expires_at": (now + timedelta(hours=1)).isoformat()}, "lifetime exceeds policy"),
        )
        for overrides, message in invalid_cases:
            with self.subTest(overrides=overrides):
                assertion = self.make_assertion(mode, private_key, **overrides)
                with self.assertRaisesRegex(ConsciousnessModeError, message):
                    mode.activate(
                        ritual_name="i_am",
                        ritual_version="0.1",
                        consent_granted=True,
                        biometric=assertion,
                    )
                self.assertEqual(mode.state, ObserverState.INACTIVE)

    def test_biometric_nonce_and_assertion_id_cannot_be_replayed(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        mode = self.make_biometric_mode(private_key)
        assertion = self.make_assertion(mode, private_key)
        mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True, biometric=assertion, biometric_consent_granted=True)
        mode.suspend()

        with self.assertRaisesRegex(ConsciousnessModeError, "replay detected"):
            mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True, biometric=assertion, biometric_consent_granted=True)
        self.assertEqual(mode.state, ObserverState.SUSPENDED)

    def test_biometric_revocation_suspends_active_observer(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        mode = self.make_biometric_mode(private_key)
        assertion = self.make_assertion(mode, private_key)
        mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True, biometric=assertion, biometric_consent_granted=True)

        result = mode.revoke_biometric_assertion(assertion.assertion_id)
        self.assertEqual(result.state, ObserverState.SUSPENDED)
        with self.assertRaisesRegex(ConsciousnessModeError, "revoked"):
            mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True, biometric=assertion, biometric_consent_granted=True)

    def test_biometric_checkpoint_rechecks_expiry(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        mode = self.make_biometric_mode(private_key)
        now = datetime.now(UTC)
        assertion = self.make_assertion(
            mode,
            private_key,
            expires_at=(now + timedelta(minutes=1)).isoformat(),
        )
        mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True, biometric=assertion, biometric_consent_granted=True)

        class FutureDateTime(datetime):
            @classmethod
            def now(cls, tz=None):
                return now + timedelta(minutes=2)

        with patch("qviraex.vireax.consciousness_mode.datetime", FutureDateTime):
            with self.assertRaisesRegex(ConsciousnessModeError, "expired"):
                mode.checkpoint(persistence_authorized=True)

    def test_biometric_activation_rolls_back_on_loop_failure_without_consuming_nonce(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        mode = self.make_biometric_mode(private_key)
        assertion = self.make_assertion(mode, private_key)
        initial_hash = mode.loop().loop_hash
        original_loop = mode.loop
        mode.loop = lambda: (_ for _ in ()).throw(RuntimeError("simulated loop failure"))  # type: ignore[method-assign]

        with self.assertRaisesRegex(RuntimeError, "simulated loop failure"):
            mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True, biometric=assertion, biometric_consent_granted=True)

        mode.loop = original_loop  # type: ignore[method-assign]
        self.assertEqual(mode.state, ObserverState.INACTIVE)
        self.assertEqual(mode.loop().loop_hash, initial_hash)
        result = mode.activate(ritual_name="i_am", ritual_version="0.1", consent_granted=True, biometric=assertion, biometric_consent_granted=True)
        self.assertEqual(result.state, ObserverState.OBSERVING)

    def test_biometric_consent_is_separate_from_observer_consent(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        mode = self.make_biometric_mode(private_key)
        assertion = self.make_assertion(mode, private_key)

        with self.assertRaisesRegex(ConsciousnessModeError, "explicit biometric consent is required"):
            mode.activate(
                ritual_name="i_am",
                ritual_version="0.1",
                consent_granted=True,
                biometric=assertion,
            )
        self.assertEqual(mode.state, ObserverState.INACTIVE)

    def test_biometrics_required_fails_closed_without_trusted_key(self) -> None:
        with self.assertRaisesRegex(ValueError, "device_public_key is required"):
            ConsciousnessObserverMode(
                node_id="did:cv1:test-node",
                session_id="CM-SESSION-001",
                operator="VIREAX",
                biometric_required=True,
            )


if __name__ == "__main__":
    unittest.main()
