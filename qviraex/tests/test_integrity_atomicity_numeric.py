from __future__ import annotations

import base64
import math
import secrets
import unittest
from datetime import UTC, datetime, timedelta
from dataclasses import replace
from unittest.mock import patch

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from qviraex.cognitive.continuum import CognitiveContinuum
from qviraex.cognitive.signal_bus import CognitiveSignalBus
from qviraex.existence.schemas import (
    AuthorizedSession,
    EpistemicClass,
    LifecycleState,
    VerifiedIdentityContext,
)
from qviraex.identity.capsule import IdentityCapsuleError, IdentityCapsuleVerifier, capsule_hash
from qviraex.mkultra_v03 import MKultraRuntime
from qviraex.vireax.consciousness_mode import (
    BiometricAssertion,
    ConsciousnessModeError,
    ConsciousnessObserverMode,
    EpistemicClass as ObserverEpistemicClass,
    InformationPacket,
    ObserverState,
)

HUGE_INT = 10**400


def case_name(value: object) -> str:
    if isinstance(value, int) and not isinstance(value, bool):
        return f"int(bits={value.bit_length()}, sign={-1 if value < 0 else 1})"
    return f"{type(value).__name__}:{value!r}"


def make_identity() -> VerifiedIdentityContext:
    return VerifiedIdentityContext(
        node_id="did:cv1:integrity-focus",
        capsule_id="sha256:" + "a" * 64,
        member_id="CV1-MEMBER-INTEGRITY",
        genesis_hash="sha256:" + "b" * 64,
        key_fingerprint="sha256:" + "c" * 64,
        lifecycle_state=LifecycleState.ACTIVE,
        consent_active=True,
    )


def make_runtime(
    *,
    persistence_authorized: bool = False,
    biometric_required: bool = False,
    device_public_key: str | bytes | None = None,
) -> MKultraRuntime:
    identity = make_identity()
    session = AuthorizedSession(
        session_id="MK03-INTEGRITY-FOCUS",
        runtime_id="RUNTIME-INTEGRITY-FOCUS",
        operator="VIREAX",
        node_id=identity.node_id,
        persistence_authorized=persistence_authorized,
        external_actions_authorized=False,
    )
    return MKultraRuntime(
        identity=identity,
        session=session,
        checkpoint_interval=1,
        biometric_required=biometric_required,
        device_public_key=device_public_key,
    )


def valid_capsule() -> dict[str, object]:
    capsule: dict[str, object] = {
        "member_id": "CV1-MEMBER-INTEGRITY",
        "node_id": "did:cv1:integrity-focus",
        "capsule_id": "pending",
        "genesis_hash": "sha256:" + "1" * 64,
        "root_key_fingerprint": "sha256:" + "2" * 64,
        "lifecycle_state": "ACTIVE",
        "consent_active": True,
        "signatures": {"member": "test-only"},
    }
    capsule["capsule_id"] = capsule_hash(capsule)
    return capsule



def make_signed_biometric_assertion(
    runtime: MKultraRuntime,
    private_key: Ed25519PrivateKey,
) -> BiometricAssertion:
    now = datetime.now(UTC)
    unsigned = BiometricAssertion(
        assertion_id="bio-" + secrets.token_hex(8),
        node_id=runtime.identity.node_id,
        session_id=runtime.session.session_id,
        operator=runtime.session.operator,
        method="local_face_match",
        confidence=0.95,
        liveness_passed=True,
        template_hash="sha256:" + "d" * 64,
        nonce=secrets.token_urlsafe(32),
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=1)).isoformat(),
        signature="unsigned-placeholder",
    )
    signature = base64.b64encode(private_key.sign(unsigned.canonical_payload())).decode("ascii")
    return replace(unsigned, signature=signature)


class BiometricRuntimeIntegrationTests(unittest.TestCase):
    def make_biometric_runtime(self, private_key: Ed25519PrivateKey) -> MKultraRuntime:
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        return make_runtime(biometric_required=True, device_public_key=public_key)

    def test_runtime_activation_passes_assertion_to_observer(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        runtime = self.make_biometric_runtime(private_key)

        with self.assertRaisesRegex(ConsciousnessModeError, "biometric assertion required"):
            runtime.activate()
        self.assertEqual(runtime.observer.state, ObserverState.INACTIVE)

        assertion = make_signed_biometric_assertion(runtime, private_key)
        runtime.activate(biometric=assertion, biometric_consent_granted=True)
        self.assertEqual(runtime.observer.state, ObserverState.OBSERVING)
        self.assertTrue(runtime.observer.signal()["biometric_verified"])

    def test_runtime_can_revoke_biometric_consent(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        runtime = self.make_biometric_runtime(private_key)
        runtime.activate(
            biometric=make_signed_biometric_assertion(runtime, private_key),
            biometric_consent_granted=True,
        )

        runtime.revoke_biometric_consent()
        self.assertEqual(runtime.observer.state, ObserverState.SUSPENDED)
        self.assertFalse(runtime.observer.signal()["biometric_verified"])
        self.assertFalse(runtime.observer.signal()["biometric_consent_active"])

    def test_runtime_transaction_restores_active_assertion_on_publish_failure(self) -> None:
        private_key = Ed25519PrivateKey.generate()
        runtime = self.make_biometric_runtime(private_key)
        assertion = make_signed_biometric_assertion(runtime, private_key)

        with patch.object(runtime.signal_bus, "publish", side_effect=RuntimeError("publish failed")):
            with self.assertRaisesRegex(RuntimeError, "publish failed"):
                runtime.activate(biometric=assertion, biometric_consent_granted=True)

        self.assertEqual(runtime.observer.state, ObserverState.INACTIVE)
        self.assertFalse(runtime.observer.signal()["biometric_verified"])

        # The failed transaction consumes the prior nonce conservatively; a fresh
        # matcher assertion can activate the rolled-back runtime.
        runtime.activate(biometric=make_signed_biometric_assertion(runtime, private_key), biometric_consent_granted=True)
        self.assertTrue(runtime.observer.signal()["biometric_verified"])


class HashChainIntegrityTests(unittest.TestCase):
    def test_signal_snapshot_detects_payload_tampering(self) -> None:
        bus = CognitiveSignalBus(node_id="did:cv1:integrity-focus")
        bus.publish(
            signal_type="test.one",
            payload={"nested": {"value": 1}},
            epistemic_class=EpistemicClass.OBSERVATION,
        )
        bus.publish(
            signal_type="test.two",
            payload={"value": 2},
            epistemic_class=EpistemicClass.EVIDENCE,
        )
        snapshot = bus.snapshot()
        anchor_head = bus.head_hash
        anchor_length = bus.sequence

        self.assertTrue(
            CognitiveSignalBus.verify_snapshot(
                snapshot,
                expected_node_id="did:cv1:integrity-focus",
                expected_head_hash=anchor_head,
                expected_length=anchor_length,
            )
        )
        snapshot[0].payload["nested"]["value"] = 99
        self.assertFalse(
            CognitiveSignalBus.verify_snapshot(
                snapshot,
                expected_node_id="did:cv1:integrity-focus",
                expected_head_hash=anchor_head,
                expected_length=anchor_length,
            )
        )

    def test_truncation_requires_external_head_and_length_anchor(self) -> None:
        bus = CognitiveSignalBus(node_id="did:cv1:integrity-focus")
        for index in range(3):
            bus.publish(
                signal_type=f"test.{index}",
                payload={"index": index},
                epistemic_class=EpistemicClass.OBSERVATION,
            )
        snapshot = bus.snapshot()

        self.assertTrue(CognitiveSignalBus.verify_snapshot(snapshot[:-1]))
        self.assertFalse(
            CognitiveSignalBus.verify_snapshot(
                snapshot[:-1],
                expected_head_hash=bus.head_hash,
                expected_length=bus.sequence,
            )
        )

    def test_checkpoint_chain_detects_tampering_and_truncation(self) -> None:
        runtime = make_runtime(persistence_authorized=True)
        runtime.activate()
        runtime.ingest(
            content="first packet",
            source="unit-test",
            epistemic_class=EpistemicClass.EVIDENCE,
            confidence=0.8,
            provenance_hash="sha256:first",
        )
        first = runtime.checkpoint()
        runtime.ingest(
            content="second packet",
            source="unit-test",
            epistemic_class=EpistemicClass.EVIDENCE,
            confidence=0.7,
            provenance_hash="sha256:second",
        )
        second = runtime.checkpoint()
        anchor = runtime.integrity_anchor()

        self.assertTrue(runtime.verify_integrity(anchor))
        self.assertTrue(
            ConsciousnessObserverMode.verify_checkpoint_chain(
                (first, second),
                expected_head_hash=second.checkpoint_hash,
                expected_count=2,
            )
        )

        tampered = replace(second, packet_count=second.packet_count + 1)
        self.assertFalse(
            ConsciousnessObserverMode.verify_checkpoint_chain(
                (first, tampered),
                expected_head_hash=second.checkpoint_hash,
                expected_count=2,
            )
        )
        self.assertFalse(
            ConsciousnessObserverMode.verify_checkpoint_chain(
                (first,),
                expected_head_hash=second.checkpoint_hash,
                expected_count=2,
            )
        )


class TransactionalIngestionTests(unittest.TestCase):
    def test_observer_failure_rolls_back_memory_signals_and_sequence(self) -> None:
        runtime = make_runtime()
        runtime.activate()
        before_state = runtime.state()
        before_anchor = runtime.integrity_anchor()

        with patch.object(runtime.observer, "observe", side_effect=RuntimeError("observer fault")):
            with self.assertRaisesRegex(RuntimeError, "observer fault"):
                runtime.ingest(
                    content="candidate",
                    source="fault-injection",
                    epistemic_class=EpistemicClass.HYPOTHESIS,
                    confidence=0.5,
                    provenance_hash="sha256:fault",
                )

        self.assertEqual(runtime.state(), before_state)
        self.assertEqual(runtime.integrity_anchor(), before_anchor)
        self.assertTrue(runtime.verify_integrity(before_anchor))

    def test_post_observer_failure_rolls_back_every_component(self) -> None:
        runtime = make_runtime()
        runtime.activate()
        before_state = runtime.state()
        before_anchor = runtime.integrity_anchor()

        with patch.object(
            runtime.cognitive,
            "detect_pattern",
            side_effect=RuntimeError("pattern fault"),
        ):
            with self.assertRaisesRegex(RuntimeError, "pattern fault"):
                runtime.ingest(
                    content="candidate",
                    source="fault-injection",
                    epistemic_class=EpistemicClass.HYPOTHESIS,
                    confidence=0.5,
                    provenance_hash="sha256:fault",
                    requires_resolution=True,
                )

        self.assertEqual(runtime.state(), before_state)
        self.assertEqual(runtime.integrity_anchor(), before_anchor)
        self.assertTrue(runtime.verify_integrity(before_anchor))

    def test_checkpoint_publication_failure_rolls_back_checkpoint_state(self) -> None:
        runtime = make_runtime(persistence_authorized=True)
        runtime.activate()
        runtime.ingest(
            content="checkpoint candidate",
            source="fault-injection",
            epistemic_class=EpistemicClass.OBSERVATION,
            confidence=0.5,
            provenance_hash="sha256:checkpoint",
        )
        before_state = runtime.state()
        before_anchor = runtime.integrity_anchor()

        with patch.object(runtime.signal_bus, "publish", side_effect=RuntimeError("publish fault")):
            with self.assertRaisesRegex(RuntimeError, "publish fault"):
                runtime.checkpoint()

        self.assertEqual(runtime.state(), before_state)
        self.assertEqual(runtime.integrity_anchor(), before_anchor)
        self.assertEqual(runtime.checkpoint_history, ())
        self.assertTrue(runtime.verify_integrity(before_anchor))

        checkpoint = runtime.checkpoint()
        self.assertIsNone(checkpoint.previous_checkpoint_hash)
        self.assertEqual(len(runtime.checkpoint_history), 1)

    def test_standalone_memory_publish_failure_is_atomic(self) -> None:
        bus = CognitiveSignalBus(node_id="did:cv1:integrity-focus")
        continuum = CognitiveContinuum(signal_bus=bus)

        with patch.object(bus, "publish", side_effect=RuntimeError("publish fault")):
            with self.assertRaisesRegex(RuntimeError, "publish fault"):
                continuum.remember(
                    content="candidate",
                    tags=(),
                    epistemic_class=EpistemicClass.HYPOTHESIS,
                    confidence=0.5,
                )

        self.assertEqual(continuum.short_memory, ())
        self.assertEqual(bus.sequence, 0)
        self.assertTrue(bus.verify_chain(expected_length=0))


class NumericAndConsentBoundaryTests(unittest.TestCase):
    def test_consent_rejects_numeric_truthiness_and_overflow_vectors(self) -> None:
        invalid_values: tuple[object, ...] = (
            0,
            1,
            -1,
            0.0,
            1.0,
            float("inf"),
            float("-inf"),
            float("nan"),
            HUGE_INT,
        )
        verifier = IdentityCapsuleVerifier(lambda _: True)

        for value in invalid_values:
            with self.subTest(value=case_name(value)):
                capsule = valid_capsule()
                expected_hash = str(capsule["capsule_id"])
                capsule["consent_active"] = value
                with self.assertRaisesRegex(IdentityCapsuleError, "JSON boolean"):
                    verifier.verify(capsule, expected_document_hash=expected_hash)

    def test_session_authority_rejects_numeric_boolean_substitutes(self) -> None:
        for value in (0, 1, 0.0, 1.0, float("inf"), HUGE_INT):
            with self.subTest(value=case_name(value)):
                with self.assertRaisesRegex(TypeError, "persistence_authorized"):
                    AuthorizedSession(
                        session_id="SESSION",
                        runtime_id="RUNTIME",
                        operator="VIREAX",
                        node_id="did:cv1:integrity-focus",
                        persistence_authorized=value,  # type: ignore[arg-type]
                        external_actions_authorized=False,
                    )

    def test_observer_checkpoint_requires_exact_boolean(self) -> None:
        observer = ConsciousnessObserverMode(
            node_id="did:cv1:integrity-focus",
            session_id="SESSION",
            operator="VIREAX",
        )
        observer.activate(
            ritual_name="i_am",
            ritual_version="0.1",
            consent_granted=True,
        )

        for value in ("false", 0, 1, 1.0):
            with self.subTest(value=case_name(value)):
                with self.assertRaisesRegex(TypeError, "persistence_authorized"):
                    observer.checkpoint(persistence_authorized=value)  # type: ignore[arg-type]

    def test_information_packet_rejects_precision_and_overflow_edges(self) -> None:
        accepted = math.nextafter(1.0, 0.0)
        packet = InformationPacket(
            packet_id="PACKET-OK",
            source="unit-test",
            content="accepted boundary",
            epistemic_class=ObserverEpistemicClass.OBSERVATION,
            confidence=accepted,
            provenance_hash="sha256:accepted",
        )
        self.assertEqual(packet.confidence, accepted)

        invalid_values: tuple[object, ...] = (
            True,
            math.nextafter(1.0, 2.0),
            math.nextafter(0.0, -1.0),
            float("inf"),
            float("-inf"),
            float("nan"),
            HUGE_INT,
        )
        for value in invalid_values:
            with self.subTest(value=case_name(value)):
                with self.assertRaises((TypeError, ValueError)):
                    InformationPacket(
                        packet_id="PACKET-BAD",
                        source="unit-test",
                        content="rejected boundary",
                        epistemic_class=ObserverEpistemicClass.OBSERVATION,
                        confidence=value,  # type: ignore[arg-type]
                        provenance_hash="sha256:rejected",
                    )

    def test_runtime_overflow_failure_is_controlled_and_non_mutating(self) -> None:
        runtime = make_runtime()
        runtime.activate()
        before_state = runtime.state()
        before_anchor = runtime.integrity_anchor()

        with self.assertRaisesRegex(ValueError, "finite float range"):
            runtime.ingest(
                content="overflow candidate",
                source="unit-test",
                epistemic_class=EpistemicClass.HYPOTHESIS,
                confidence=HUGE_INT,
                provenance_hash="sha256:overflow",
            )

        self.assertEqual(runtime.state(), before_state)
        self.assertEqual(runtime.integrity_anchor(), before_anchor)

    def test_requires_resolution_rejects_numeric_truthiness(self) -> None:
        with self.assertRaisesRegex(TypeError, "requires_resolution"):
            InformationPacket(
                packet_id="PACKET-BOOL",
                source="unit-test",
                content="candidate",
                epistemic_class=ObserverEpistemicClass.OBSERVATION,
                confidence=0.5,
                provenance_hash="sha256:test",
                requires_resolution=1,  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
