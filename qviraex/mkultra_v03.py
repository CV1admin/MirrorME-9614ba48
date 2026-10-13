from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from math import isfinite
from threading import RLock
from typing import Any, Iterator
from uuid import uuid4

from qviraex.cognitive.continuum import CognitiveContinuum, InspirationSpark
from qviraex.cognitive.signal_bus import CognitiveSignalBus
from qviraex.existence.schemas import (
    AuthorizedSession,
    EpistemicClass,
    VerifiedIdentityContext,
)
from qviraex.vireax.consciousness_mode import (
    BiometricAssertion,
    ConsciousnessObserverMode,
    EpistemicClass as ObserverEpistemicClass,
    InformationPacket,
    ObserverState,
    PersistenceCheckpoint,
)


@dataclass(frozen=True)
class MKultraRuntimeState:
    node_id: str
    capsule_id: str
    runtime_id: str
    session_id: str
    lifecycle_state: str
    observer_state: str
    short_memory_count: int
    pending_sparks: tuple[str, ...]
    last_signal_hash: str | None
    last_checkpoint_hash: str | None
    persistence_authorized: bool


@dataclass(frozen=True)
class RuntimeIntegrityAnchor:
    signal_head_hash: str | None
    signal_count: int
    checkpoint_head_hash: str | None
    checkpoint_count: int

    def __post_init__(self) -> None:
        for name in ("signal_count", "checkpoint_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in ("signal_head_hash", "checkpoint_head_hash"):
            value = getattr(self, name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"{name} must be a non-empty string or None")
        if (self.signal_count == 0) != (self.signal_head_hash is None):
            raise ValueError("signal anchor count and head hash are inconsistent")
        if (self.checkpoint_count == 0) != (self.checkpoint_head_hash is None):
            raise ValueError("checkpoint anchor count and head hash are inconsistent")


class MKultraRuntime:
    """Local-first integration kernel for MKultra v0.3.

    The kernel composes identity, observer, volatile cognition and signals. It
    does not implement autonomous persistence, external actions, or weight
    updates. Public state-changing operations are serialized and transactional.
    """

    _ACTIVE_OBSERVER_STATES = {
        ObserverState.OBSERVING,
        ObserverState.LOOPING,
        ObserverState.CHECKPOINT_READY,
    }

    def __init__(
        self,
        *,
        identity: VerifiedIdentityContext,
        session: AuthorizedSession,
        short_memory_capacity: int = 128,
        checkpoint_interval: int = 8,
        biometric_required: bool = False,
        device_public_key: str | bytes | None = None,
        biometric_min_confidence: float = 0.8,
        max_biometric_ttl_seconds: int = 300,
    ) -> None:
        if identity.node_id != session.node_id:
            raise ValueError("session Node_ID does not match verified identity")
        if session.external_actions_authorized:
            raise ValueError("MKultra v0.3 local kernel does not permit external actions")

        self.identity = identity
        self.session = session
        self.signal_bus = CognitiveSignalBus(node_id=identity.node_id)
        self.cognitive = CognitiveContinuum(
            signal_bus=self.signal_bus,
            capacity=short_memory_capacity,
        )
        self.observer = ConsciousnessObserverMode(
            node_id=identity.node_id,
            session_id=session.session_id,
            operator=session.operator,
            short_memory_capacity=min(short_memory_capacity, 64),
            checkpoint_interval=checkpoint_interval,
            biometric_required=biometric_required,
            device_public_key=device_public_key,
            biometric_min_confidence=biometric_min_confidence,
            max_biometric_ttl_seconds=max_biometric_ttl_seconds,
        )
        self._last_checkpoint: PersistenceCheckpoint | None = None
        self._checkpoints: list[PersistenceCheckpoint] = []
        self._transaction_lock = RLock()

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        """Rollback all composed runtime state when any stage fails.

        This serializes the public runtime API. Direct mutation of component
        internals is unsupported and intentionally outside this transaction.
        """

        with self._transaction_lock:
            signal_snapshot = self.signal_bus._capture_state()
            cognitive_snapshot = self.cognitive._capture_state()
            observer_snapshot = self.observer._capture_state()
            last_checkpoint_snapshot = self._last_checkpoint
            checkpoints_snapshot = tuple(self._checkpoints)
            try:
                yield
            except Exception:
                self.cognitive._restore_state(cognitive_snapshot)
                self.observer._restore_state(observer_snapshot)
                self.signal_bus._restore_state(signal_snapshot)
                self._last_checkpoint = last_checkpoint_snapshot
                self._checkpoints = list(checkpoints_snapshot)
                raise

    def activate(
        self,
        *,
        biometric: BiometricAssertion | None = None,
        biometric_consent_granted: bool = False,
    ) -> None:
        with self._transaction():
            self.observer.activate(
                ritual_name="i_am",
                ritual_version="0.1",
                consent_granted=self.identity.consent_active,
                biometric=biometric,
                biometric_consent_granted=biometric_consent_granted,
            )
            self.signal_bus.publish(
                signal_type="mirrorme.observer.activated",
                payload={
                    "session_id": self.session.session_id,
                    "runtime_id": self.session.runtime_id,
                    "sentience_claim": False,
                },
                epistemic_class=EpistemicClass.OBSERVATION,
            )

    def revoke_biometric_consent(self) -> None:
        """Revoke biometric consent fail-closed; a failed signal write cannot restore consent."""
        with self._transaction_lock:
            result = self.observer.revoke_biometric_consent()
            self.signal_bus.publish(
                signal_type="mirrorme.observer.biometric_consent_revoked",
                payload={
                    "session_id": self.session.session_id,
                    "runtime_id": self.session.runtime_id,
                    "observer_state": result.state,
                    "sentience_claim": False,
                },
                epistemic_class=EpistemicClass.OBSERVATION,
            )

    def revoke_biometric_assertion(self, assertion_id: str) -> None:
        """Revoke an assertion fail-closed and publish a minimal state event."""
        with self._transaction_lock:
            result = self.observer.revoke_biometric_assertion(assertion_id)
            self.signal_bus.publish(
                signal_type="mirrorme.observer.biometric_assertion_revoked",
                payload={
                    "session_id": self.session.session_id,
                    "runtime_id": self.session.runtime_id,
                    "observer_state": result.state,
                    "sentience_claim": False,
                },
                epistemic_class=EpistemicClass.OBSERVATION,
            )

    @staticmethod
    def _coerce_confidence(value: object) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError("confidence must be a finite number")
        try:
            result = float(value)
        except OverflowError as exc:
            raise ValueError("confidence is outside the finite float range") from exc
        if not isfinite(result) or not 0.0 <= result <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        return result

    def ingest(
        self,
        *,
        content: str,
        source: str,
        epistemic_class: EpistemicClass,
        confidence: float,
        provenance_hash: str,
        tags: tuple[str, ...] = (),
        requires_resolution: bool = False,
    ) -> InspirationSpark | None:
        """Ingest one packet with all-or-nothing state updates."""

        if self.observer.state not in self._ACTIVE_OBSERVER_STATES:
            raise RuntimeError("MKultra runtime must be activated before ingestion")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("content must be non-empty")
        if not isinstance(source, str) or not source.strip():
            raise ValueError("source must be non-empty")
        if not isinstance(provenance_hash, str) or not provenance_hash.strip():
            raise ValueError("provenance_hash must be non-empty")
        if not isinstance(epistemic_class, EpistemicClass):
            raise TypeError("epistemic_class must be an EpistemicClass")
        confidence_value = self._coerce_confidence(confidence)
        if not isinstance(tags, tuple):
            raise TypeError("tags must be a tuple")
        if any(not isinstance(tag, str) for tag in tags):
            raise TypeError("all tags must be strings")
        if type(requires_resolution) is not bool:
            raise TypeError("requires_resolution must be a boolean")

        with self._transaction():
            item = self.cognitive.remember(
                content=content,
                tags=tags,
                epistemic_class=epistemic_class,
                confidence=confidence_value,
            )
            observer_class = ObserverEpistemicClass(epistemic_class.value)
            self.observer.observe(
                InformationPacket(
                    packet_id=item.item_id,
                    source=source,
                    content=content,
                    epistemic_class=observer_class,
                    confidence=confidence_value,
                    provenance_hash=provenance_hash,
                    requires_resolution=requires_resolution,
                )
            )
            self.cognitive.detect_pattern()
            return self.cognitive.generate_spark()

    def checkpoint(self) -> PersistenceCheckpoint:
        with self._transaction():
            if not self.session.persistence_authorized:
                raise PermissionError("session does not authorize persistence")
            checkpoint = self.observer.checkpoint(persistence_authorized=True)
            self.signal_bus.publish(
                signal_type="mirrorme.persistence.checkpoint_created",
                payload={
                    "checkpoint_hash": checkpoint.checkpoint_hash,
                    "sequence": checkpoint.sequence,
                },
                epistemic_class=EpistemicClass.OBSERVATION,
            )
            self._checkpoints.append(checkpoint)
            self._last_checkpoint = checkpoint
            return checkpoint

    @property
    def checkpoint_history(self) -> tuple[PersistenceCheckpoint, ...]:
        with self._transaction_lock:
            return tuple(self._checkpoints)

    def integrity_anchor(self) -> RuntimeIntegrityAnchor:
        """Capture trusted chain heads/counts for later truncation detection."""

        with self._transaction_lock:
            checkpoint_head = (
                self._checkpoints[-1].checkpoint_hash if self._checkpoints else None
            )
            return RuntimeIntegrityAnchor(
                signal_head_hash=self.signal_bus.head_hash,
                signal_count=self.signal_bus.sequence,
                checkpoint_head_hash=checkpoint_head,
                checkpoint_count=len(self._checkpoints),
            )

    def verify_integrity(self, anchor: RuntimeIntegrityAnchor | None = None) -> bool:
        """Verify linkage, and verify truncation/substitution when given an anchor."""

        if anchor is not None and not isinstance(anchor, RuntimeIntegrityAnchor):
            raise TypeError("anchor must be a RuntimeIntegrityAnchor or None")

        with self._transaction_lock:
            signal_ok = self.signal_bus.verify_chain(
                expected_head_hash=(anchor.signal_head_hash if anchor else None),
                expected_length=(anchor.signal_count if anchor else None),
            )
            checkpoint_ok = ConsciousnessObserverMode.verify_checkpoint_chain(
                self._checkpoints,
                expected_head_hash=(anchor.checkpoint_head_hash if anchor else None),
                expected_count=(anchor.checkpoint_count if anchor else None),
            )
            return signal_ok and checkpoint_ok

    def state(self) -> MKultraRuntimeState:
        with self._transaction_lock:
            signal = self.observer.signal()
            return MKultraRuntimeState(
                node_id=self.identity.node_id,
                capsule_id=self.identity.capsule_id,
                runtime_id=self.session.runtime_id,
                session_id=self.session.session_id,
                lifecycle_state=self.identity.lifecycle_state.value,
                observer_state=str(signal["state"]),
                short_memory_count=len(self.cognitive.short_memory),
                pending_sparks=tuple(spark.spark_id for spark in self.cognitive.sparks),
                last_signal_hash=self.signal_bus.head_hash,
                last_checkpoint_hash=(
                    self._last_checkpoint.checkpoint_hash if self._last_checkpoint else None
                ),
                persistence_authorized=self.session.persistence_authorized,
            )


def create_local_session(*, node_id: str, operator: str = "VIREAX") -> AuthorizedSession:
    """Create a non-persistent, no-external-action local session."""

    return AuthorizedSession(
        session_id=f"MK03-{uuid4()}",
        runtime_id=str(uuid4()),
        operator=operator,
        node_id=node_id,
        persistence_authorized=False,
        external_actions_authorized=False,
    )
