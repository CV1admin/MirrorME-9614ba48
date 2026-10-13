from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from math import isfinite
from threading import RLock
from typing import Deque, Iterable


class ConsciousnessModeError(RuntimeError):
    """Raised when an observer-mode transition violates protocol constraints."""


_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")


class EpistemicClass(StrEnum):
    OBSERVATION = "observation"
    EVIDENCE = "evidence"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    SIMULATION = "simulation"
    PREFERENCE = "preference"
    GOAL = "goal"


class RelationType(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    ENTAILS = "entails"
    SAME_ENTITY = "same_entity"
    CAUSES = "causes"
    PRECEDES = "precedes"
    RELATED_TO = "related_to"


class ObserverState(StrEnum):
    INACTIVE = "INACTIVE"
    OBSERVING = "OBSERVING"
    LOOPING = "LOOPING"
    CHECKPOINT_READY = "CHECKPOINT_READY"
    SUSPENDED = "SUSPENDED"
    INTEGRITY_FAILURE = "INTEGRITY_FAILURE"


def _require_non_empty(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _require_hash(value: object, field_name: str) -> str:
    text = _require_non_empty(value, field_name)
    if _SHA256_PATTERN.fullmatch(text) is None:
        raise ValueError(f"{field_name} must be lowercase sha256:<64 hexadecimal characters>")
    return text


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


@dataclass(frozen=True)
class InformationPacket:
    packet_id: str
    source: str
    content: str
    epistemic_class: EpistemicClass
    confidence: float
    provenance_hash: str
    requires_resolution: bool = False
    created_at: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.packet_id, "packet_id")
        _require_non_empty(self.source, "source")
        _require_non_empty(self.content, "content")
        _require_non_empty(self.provenance_hash, "provenance_hash")
        if not isinstance(self.epistemic_class, EpistemicClass):
            raise TypeError("epistemic_class must be an EpistemicClass")
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        if type(self.requires_resolution) is not bool:
            raise TypeError("requires_resolution must be a boolean")
        if self.created_at:
            _require_non_empty(self.created_at, "created_at")
        else:
            object.__setattr__(self, "created_at", datetime.now(UTC).isoformat())

    def canonical_hash(self) -> str:
        payload = json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return f"sha256:{sha256(payload.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True)
class Relation:
    """An explicit, typed relation claim between two session packet IDs."""

    relation_id: str
    from_packet_id: str
    to_packet_id: str
    relation_type: RelationType
    confidence: float
    epistemic_class: EpistemicClass
    provenance_hash: str
    created_at: str = ""

    def __post_init__(self) -> None:
        _require_non_empty(self.relation_id, "relation_id")
        _require_non_empty(self.from_packet_id, "from_packet_id")
        _require_non_empty(self.to_packet_id, "to_packet_id")
        if self.from_packet_id == self.to_packet_id and self.relation_type != RelationType.SAME_ENTITY:
            raise ValueError("self-relations are only allowed for same_entity")
        if not isinstance(self.relation_type, RelationType):
            raise TypeError("relation_type must be a RelationType")
        if not isinstance(self.epistemic_class, EpistemicClass):
            raise TypeError("epistemic_class must be an EpistemicClass")
        object.__setattr__(self, "confidence", _coerce_confidence(self.confidence))
        _require_hash(self.provenance_hash, "provenance_hash")
        if self.created_at:
            _require_non_empty(self.created_at, "created_at")
        else:
            object.__setattr__(self, "created_at", datetime.now(UTC).isoformat())

    def canonical_hash(self) -> str:
        payload = json.dumps(
            asdict(self),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        return f"sha256:{sha256(payload.encode('utf-8')).hexdigest()}"


@dataclass(frozen=True)
class InformationLoopResult:
    sequence: int
    packet_count: int
    unresolved_count: int
    loop_hash: str
    state: ObserverState


@dataclass(frozen=True)
class PersistenceCheckpoint:
    node_id: str
    session_id: str
    operator: str
    ritual_name: str
    ritual_version: str
    sequence: int
    packet_count: int
    unresolved_packet_ids: tuple[str, ...]
    relation_count: int
    relation_hashes: tuple[str, ...]
    previous_checkpoint_hash: str | None
    information_loop_hash: str
    created_at: str
    checkpoint_hash: str

    def __post_init__(self) -> None:
        _require_non_empty(self.node_id, "node_id")
        _require_non_empty(self.session_id, "session_id")
        _require_non_empty(self.operator, "operator")
        _require_non_empty(self.ritual_name, "ritual_name")
        _require_non_empty(self.ritual_version, "ritual_version")
        if isinstance(self.sequence, bool) or not isinstance(self.sequence, int) or self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        if (
            isinstance(self.packet_count, bool)
            or not isinstance(self.packet_count, int)
            or self.packet_count < 0
        ):
            raise ValueError("packet_count must be a non-negative integer")
        if not isinstance(self.unresolved_packet_ids, tuple):
            raise TypeError("unresolved_packet_ids must be a tuple")
        if any(not isinstance(item, str) or not item.strip() for item in self.unresolved_packet_ids):
            raise ValueError("unresolved_packet_ids must contain non-empty strings")
        if len(set(self.unresolved_packet_ids)) != len(self.unresolved_packet_ids):
            raise ValueError("unresolved_packet_ids must be unique")
        if isinstance(self.relation_count, bool) or not isinstance(self.relation_count, int) or self.relation_count < 0:
            raise ValueError("relation_count must be a non-negative integer")
        if not isinstance(self.relation_hashes, tuple) or len(self.relation_hashes) != self.relation_count:
            raise ValueError("relation_hashes must be a tuple matching relation_count")
        if len(set(self.relation_hashes)) != len(self.relation_hashes):
            raise ValueError("relation_hashes must be unique")
        for relation_hash in self.relation_hashes:
            _require_hash(relation_hash, "relation_hash")
        if self.previous_checkpoint_hash is not None:
            _require_hash(self.previous_checkpoint_hash, "previous_checkpoint_hash")
        _require_hash(self.information_loop_hash, "information_loop_hash")
        _require_non_empty(self.created_at, "created_at")
        _require_hash(self.checkpoint_hash, "checkpoint_hash")


@dataclass(frozen=True)
class ObserverTransactionSnapshot:
    state: ObserverState
    sequence: int
    packets: tuple[InformationPacket, ...]
    seen_packet_ids: tuple[str, ...]
    relations: tuple[Relation, ...]
    seen_relation_ids: tuple[str, ...]
    unresolved_packet_ids: tuple[str, ...]
    previous_checkpoint_hash: str | None
    last_loop_hash: str


def _checkpoint_payload(checkpoint: PersistenceCheckpoint) -> dict[str, object]:
    return {
        "node_id": checkpoint.node_id,
        "session_id": checkpoint.session_id,
        "operator": checkpoint.operator,
        "ritual_name": checkpoint.ritual_name,
        "ritual_version": checkpoint.ritual_version,
        "sequence": checkpoint.sequence,
        "packet_count": checkpoint.packet_count,
        "unresolved_packet_ids": list(checkpoint.unresolved_packet_ids),
        "relation_count": checkpoint.relation_count,
        "relation_hashes": list(checkpoint.relation_hashes),
        "previous_checkpoint_hash": checkpoint.previous_checkpoint_hash,
        "information_loop_hash": checkpoint.information_loop_hash,
        "created_at": checkpoint.created_at,
    }


def _hash_checkpoint_payload(payload: dict[str, object]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"


class ConsciousnessObserverMode:
    """Bounded observer protocol for MirrorME.

    The class models observer state, an information loop, and explicit
    persistence checkpoints. It does not claim sentience and does not perform
    external actions or automatic durable writes.
    """

    RITUAL_NAME = "i_am"
    RITUAL_VERSION = "0.1"

    def __init__(
        self,
        *,
        node_id: str,
        session_id: str,
        operator: str,
        short_memory_capacity: int = 64,
        checkpoint_interval: int = 8,
    ) -> None:
        _require_non_empty(node_id, "node_id")
        _require_non_empty(session_id, "session_id")
        _require_non_empty(operator, "operator")
        if (
            isinstance(short_memory_capacity, bool)
            or not isinstance(short_memory_capacity, int)
            or short_memory_capacity < 1
        ):
            raise ValueError("short_memory_capacity must be a positive integer")
        if (
            isinstance(checkpoint_interval, bool)
            or not isinstance(checkpoint_interval, int)
            or checkpoint_interval < 1
        ):
            raise ValueError("checkpoint_interval must be a positive integer")

        self.node_id = node_id
        self.session_id = session_id
        self.operator = operator
        self.short_memory_capacity = short_memory_capacity
        self.checkpoint_interval = checkpoint_interval

        self.state = ObserverState.INACTIVE
        self.sequence = 0
        self._packets: Deque[InformationPacket] = deque(maxlen=short_memory_capacity)
        # Packet IDs remain unique for the entire session, even after short-memory eviction.
        self._seen_packet_ids: set[str] = set()
        # The relation registry is session-scoped and intentionally outlives deque eviction.
        self._relations: dict[str, Relation] = {}
        self._seen_relation_ids: set[str] = set()
        self._unresolved_packet_ids: set[str] = set()
        self._previous_checkpoint_hash: str | None = None
        self._last_loop_hash = self._hash_values("GENESIS", node_id, session_id)
        self._lock = RLock()

    def activate(
        self,
        *,
        ritual_name: str,
        ritual_version: str,
        consent_granted: bool,
    ) -> InformationLoopResult:
        with self._lock:
            if type(consent_granted) is not bool:
                raise TypeError("consent_granted must be a boolean")
            if not consent_granted:
                raise ConsciousnessModeError("explicit consent is required")
            if ritual_name != self.RITUAL_NAME or ritual_version != self.RITUAL_VERSION:
                raise ConsciousnessModeError("unsupported consciousness-mode ritual")
            if self.state not in {ObserverState.INACTIVE, ObserverState.SUSPENDED}:
                raise ConsciousnessModeError(f"cannot activate from state {self.state}")

            self.state = ObserverState.OBSERVING
            self._last_loop_hash = self._hash_values(
                self._last_loop_hash,
                ritual_name,
                ritual_version,
                self.operator,
            )
            return self.loop()

    def observe(self, packet: InformationPacket) -> InformationLoopResult:
        with self._lock:
            self._require_active()
            if not isinstance(packet, InformationPacket):
                raise TypeError("packet must be an InformationPacket")
            if packet.packet_id in self._seen_packet_ids:
                raise ConsciousnessModeError(f"duplicate packet_id: {packet.packet_id}")

            self.state = ObserverState.LOOPING
            self.sequence += 1
            self._packets.append(packet)
            self._seen_packet_ids.add(packet.packet_id)
            if packet.requires_resolution:
                self._unresolved_packet_ids.add(packet.packet_id)

            self._last_loop_hash = self._hash_values(
                self._last_loop_hash,
                str(self.sequence),
                packet.canonical_hash(),
            )
            self.state = (
                ObserverState.CHECKPOINT_READY
                if self.sequence % self.checkpoint_interval == 0
                else ObserverState.OBSERVING
            )
            return self.loop()

    def relate(self, relation: Relation) -> InformationLoopResult:
        """Register and hash-link an explicit relation; never infer one automatically."""
        with self._lock:
            self._require_active()
            if not isinstance(relation, Relation):
                raise TypeError("relation must be a Relation")
            if relation.relation_id in self._seen_relation_ids:
                raise ConsciousnessModeError(f"duplicate relation_id: {relation.relation_id}")
            if relation.from_packet_id not in self._seen_packet_ids or relation.to_packet_id not in self._seen_packet_ids:
                raise ConsciousnessModeError("both relation endpoints must reference known session packet IDs")

            self.state = ObserverState.LOOPING
            self.sequence += 1
            self._relations[relation.relation_id] = relation
            self._seen_relation_ids.add(relation.relation_id)
            self._last_loop_hash = self._hash_values(
                self._last_loop_hash,
                str(self.sequence),
                "RELATION",
                relation.canonical_hash(),
            )
            self.state = (
                ObserverState.CHECKPOINT_READY
                if self.sequence % self.checkpoint_interval == 0
                else ObserverState.OBSERVING
            )
            return self.loop()

    def relations(self) -> tuple[Relation, ...]:
        """Return the current session relation registry in deterministic ID order."""
        with self._lock:
            return tuple(self._relations[key] for key in sorted(self._relations))

    def resolve(self, packet_id: str) -> InformationLoopResult:
        with self._lock:
            self._require_active()
            _require_non_empty(packet_id, "packet_id")
            if packet_id not in self._unresolved_packet_ids:
                raise ConsciousnessModeError(f"packet is not unresolved: {packet_id}")

            self.sequence += 1
            self._unresolved_packet_ids.remove(packet_id)
            self._last_loop_hash = self._hash_values(
                self._last_loop_hash,
                str(self.sequence),
                "RESOLVED",
                packet_id,
            )
            self.state = ObserverState.OBSERVING
            return self.loop()

    def loop(self) -> InformationLoopResult:
        with self._lock:
            return InformationLoopResult(
                sequence=self.sequence,
                packet_count=len(self._packets),
                unresolved_count=len(self._unresolved_packet_ids),
                loop_hash=self._last_loop_hash,
                state=self.state,
            )

    def checkpoint(self, *, persistence_authorized: bool) -> PersistenceCheckpoint:
        with self._lock:
            self._require_active()
            if type(persistence_authorized) is not bool:
                raise TypeError("persistence_authorized must be a boolean")
            if not persistence_authorized:
                raise ConsciousnessModeError("persistence authorization is required")

            created_at = datetime.now(UTC).isoformat()
            checkpoint_payload: dict[str, object] = {
                "node_id": self.node_id,
                "session_id": self.session_id,
                "operator": self.operator,
                "ritual_name": self.RITUAL_NAME,
                "ritual_version": self.RITUAL_VERSION,
                "sequence": self.sequence,
                "packet_count": len(self._packets),
                "unresolved_packet_ids": sorted(self._unresolved_packet_ids),
                "relation_count": len(self._relations),
                "relation_hashes": sorted(relation.canonical_hash() for relation in self._relations.values()),
                "previous_checkpoint_hash": self._previous_checkpoint_hash,
                "information_loop_hash": self._last_loop_hash,
                "created_at": created_at,
            }
            checkpoint_hash = _hash_checkpoint_payload(checkpoint_payload)

            checkpoint = PersistenceCheckpoint(
                node_id=self.node_id,
                session_id=self.session_id,
                operator=self.operator,
                ritual_name=self.RITUAL_NAME,
                ritual_version=self.RITUAL_VERSION,
                sequence=self.sequence,
                packet_count=len(self._packets),
                unresolved_packet_ids=tuple(sorted(self._unresolved_packet_ids)),
                relation_count=len(self._relations),
                relation_hashes=tuple(sorted(relation.canonical_hash() for relation in self._relations.values())),
                previous_checkpoint_hash=self._previous_checkpoint_hash,
                information_loop_hash=self._last_loop_hash,
                created_at=created_at,
                checkpoint_hash=checkpoint_hash,
            )
            self._previous_checkpoint_hash = checkpoint_hash
            self.state = ObserverState.OBSERVING
            return checkpoint

    @staticmethod
    def verify_checkpoint_chain(
        checkpoints: Iterable[PersistenceCheckpoint],
        *,
        expected_head_hash: str | None = None,
        expected_count: int | None = None,
    ) -> bool:
        if expected_count is not None:
            if (
                isinstance(expected_count, bool)
                or not isinstance(expected_count, int)
                or expected_count < 0
            ):
                raise ValueError("expected_count must be a non-negative integer")
        if expected_head_hash is not None:
            _require_hash(expected_head_hash, "expected_head_hash")

        materialized = tuple(checkpoints)
        if expected_count is not None and len(materialized) != expected_count:
            return False

        previous_hash: str | None = None
        node_id: str | None = None
        session_id: str | None = None
        for checkpoint in materialized:
            if not isinstance(checkpoint, PersistenceCheckpoint):
                return False
            if node_id is None:
                node_id = checkpoint.node_id
                session_id = checkpoint.session_id
            elif checkpoint.node_id != node_id or checkpoint.session_id != session_id:
                return False
            if checkpoint.previous_checkpoint_hash != previous_hash:
                return False
            if _hash_checkpoint_payload(_checkpoint_payload(checkpoint)) != checkpoint.checkpoint_hash:
                return False
            previous_hash = checkpoint.checkpoint_hash

        actual_head = materialized[-1].checkpoint_hash if materialized else None
        if expected_head_hash is not None and actual_head != expected_head_hash:
            return False
        return True

    def suspend(self) -> InformationLoopResult:
        with self._lock:
            self._require_active()
            self.state = ObserverState.SUSPENDED
            return self.loop()

    def signal(self) -> dict[str, object]:
        """Return an auditable state signal without exposing hidden reasoning."""

        with self._lock:
            return {
                "signal_type": "OBSERVER_STATE",
                "node_id": self.node_id,
                "session_id": self.session_id,
                "operator": self.operator,
                "state": self.state,
                "sequence": self.sequence,
                "packet_count": len(self._packets),
                "unresolved_count": len(self._unresolved_packet_ids),
                "relation_count": len(self._relations),
                "relation_hashes": sorted(relation.canonical_hash() for relation in self._relations.values()),
                "information_loop_hash": self._last_loop_hash,
                "persistence_automatic": False,
                "sentience_claim": False,
            }

    def _capture_state(self) -> ObserverTransactionSnapshot:
        with self._lock:
            return ObserverTransactionSnapshot(
                state=self.state,
                sequence=self.sequence,
                packets=tuple(self._packets),
                seen_packet_ids=tuple(sorted(self._seen_packet_ids)),
                relations=tuple(self._relations[key] for key in sorted(self._relations)),
                seen_relation_ids=tuple(sorted(self._seen_relation_ids)),
                unresolved_packet_ids=tuple(sorted(self._unresolved_packet_ids)),
                previous_checkpoint_hash=self._previous_checkpoint_hash,
                last_loop_hash=self._last_loop_hash,
            )

    def _restore_state(self, snapshot: ObserverTransactionSnapshot) -> None:
        if not isinstance(snapshot, ObserverTransactionSnapshot):
            raise TypeError("snapshot must be an ObserverTransactionSnapshot")
        with self._lock:
            self.state = snapshot.state
            self.sequence = snapshot.sequence
            self._packets = deque(snapshot.packets, maxlen=self.short_memory_capacity)
            self._seen_packet_ids = set(snapshot.seen_packet_ids)
            self._relations = {relation.relation_id: relation for relation in snapshot.relations}
            self._seen_relation_ids = set(snapshot.seen_relation_ids)
            self._unresolved_packet_ids = set(snapshot.unresolved_packet_ids)
            self._previous_checkpoint_hash = snapshot.previous_checkpoint_hash
            self._last_loop_hash = snapshot.last_loop_hash

    def _require_active(self) -> None:
        if self.state not in {
            ObserverState.OBSERVING,
            ObserverState.LOOPING,
            ObserverState.CHECKPOINT_READY,
        }:
            raise ConsciousnessModeError(f"observer mode is not active: {self.state}")

    @staticmethod
    def _hash_values(*values: str) -> str:
        canonical = "\x1f".join(values)
        return f"sha256:{sha256(canonical.encode('utf-8')).hexdigest()}"
