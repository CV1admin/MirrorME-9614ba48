from __future__ import annotations

import json
import re
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from math import isfinite
from typing import Any

from .consciousness_mode import EpistemicClass

_SHA256 = re.compile(r"^sha256:[0-9a-f]{64}$")
_GENESIS = "GENESIS"


def _non_empty(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _digest(value: object, name: str) -> str:
    result = _non_empty(value, name)
    if not _SHA256.fullmatch(result):
        raise ValueError(f"{name} must be sha256:<64 lowercase hexadecimal characters>")
    return result


def _confidence(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError("confidence must be a finite number")
    result = float(value)
    if not isfinite(result) or not 0.0 <= result <= 1.0:
        raise ValueError("confidence must be finite and in [0, 1]")
    return result


def _timestamp(value: str | None) -> str:
    if value is None:
        return datetime.now(UTC).isoformat()
    if not isinstance(value, str) or not value.strip():
        raise ValueError("observed_at must be a non-empty ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("observed_at must be a valid ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("observed_at must include an explicit timezone")
    return parsed.astimezone(UTC).isoformat()


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _hash(value: str) -> str:
    return "sha256:" + sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ContinuumEntry:
    """One provenance-preserving observer-state transition.

    Only the content digest is retained; source text is not stored. A valid chain proves
    internal consistency relative to its starting point, not truth, authorship, physical
    existence, or subjective experience.
    """
    sequence: int
    event_id: str
    source: str
    epistemic_class: EpistemicClass
    confidence: float
    observed_at: str
    content_hash: str
    state_before_hash: str | None
    state_after_hash: str
    previous_entry_hash: str
    entry_hash: str

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("sequence must be a non-negative integer")
        _non_empty(self.event_id, "event_id")
        _non_empty(self.source, "source")
        if not isinstance(self.epistemic_class, EpistemicClass):
            raise TypeError("epistemic_class must be an EpistemicClass")
        object.__setattr__(self, "confidence", _confidence(self.confidence))
        _timestamp(self.observed_at)
        _digest(self.content_hash, "content_hash")
        if self.state_before_hash is not None:
            _digest(self.state_before_hash, "state_before_hash")
        _digest(self.state_after_hash, "state_after_hash")
        if self.previous_entry_hash != _GENESIS:
            _digest(self.previous_entry_hash, "previous_entry_hash")
        _digest(self.entry_hash, "entry_hash")

    def hash_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("entry_hash")
        payload["epistemic_class"] = self.epistemic_class.value
        return payload


class ContinuumLedger:
    """Append-only state-continuity ledger with explicit epistemic labels.

    Later transitions must start at the prior state digest. The ledger refuses writes
    at capacity rather than silently evicting history.
    """

    def __init__(self, *, max_entries: int = 4096) -> None:
        if type(max_entries) is not int or max_entries < 1:
            raise ValueError("max_entries must be a positive integer")
        self.max_entries = max_entries
        self._entries: list[ContinuumEntry] = []
        self._event_ids: set[str] = set()

    @property
    def entries(self) -> tuple[ContinuumEntry, ...]:
        return tuple(self._entries)

    @property
    def head_hash(self) -> str:
        return self._entries[-1].entry_hash if self._entries else _GENESIS

    def append(
        self, *, event_id: str, source: str, content: str,
        epistemic_class: EpistemicClass, confidence: float,
        state_before_hash: str | None, state_after_hash: str,
        observed_at: str | None = None,
    ) -> ContinuumEntry:
        _non_empty(event_id, "event_id")
        _non_empty(source, "source")
        if not isinstance(content, str) or not content:
            raise ValueError("content must be a non-empty string")
        if not isinstance(epistemic_class, EpistemicClass):
            raise TypeError("epistemic_class must be an EpistemicClass")
        if event_id in self._event_ids:
            raise ValueError(f"duplicate event_id: {event_id}")
        if len(self._entries) >= self.max_entries:
            raise OverflowError("continuum ledger capacity reached; export/checkpoint before continuing")
        if not self._entries:
            if state_before_hash is not None:
                raise ValueError("first entry must have state_before_hash=None")
        elif state_before_hash != self._entries[-1].state_after_hash:
            raise ValueError("state_before_hash must equal the previous state_after_hash")

        values: dict[str, Any] = {
            "sequence": len(self._entries),
            "event_id": event_id,
            "source": source,
            "epistemic_class": epistemic_class,
            "confidence": _confidence(confidence),
            "observed_at": _timestamp(observed_at),
            "content_hash": _hash(content),
            "state_before_hash": state_before_hash,
            "state_after_hash": _digest(state_after_hash, "state_after_hash"),
            "previous_entry_hash": self.head_hash,
        }
        canonical_values = dict(values)
        canonical_values["epistemic_class"] = epistemic_class.value
        entry = ContinuumEntry(**values, entry_hash=_hash(_canonical(canonical_values)))
        self._entries.append(entry)
        self._event_ids.add(event_id)
        return entry

    def verify(self, *, expected_head_hash: str | None = None) -> bool:
        previous_hash = _GENESIS
        previous_state: str | None = None
        seen_ids: set[str] = set()
        for index, entry in enumerate(self._entries):
            if entry.sequence != index or entry.previous_entry_hash != previous_hash:
                return False
            if entry.event_id in seen_ids or entry.state_before_hash != previous_state:
                return False
            try:
                expected = _hash(_canonical(entry.hash_payload()))
            except (TypeError, ValueError):
                return False
            if entry.entry_hash != expected:
                return False
            previous_hash = entry.entry_hash
            previous_state = entry.state_after_hash
            seen_ids.add(entry.event_id)
        return expected_head_hash is None or previous_hash == expected_head_hash

    def continuity_report(self) -> dict[str, Any]:
        valid = self.verify()
        return {
            "valid": valid,
            "entry_count": len(self._entries),
            "head_hash": self.head_hash,
            "state_chain_linked": valid,
            "epistemic_classes": [entry.epistemic_class.value for entry in self._entries],
            "truth_assessed": False,
            "subjective_experience_assessed": False,
        }
