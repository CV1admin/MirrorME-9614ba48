from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class AuditRecord:
    index: int
    payload: dict[str, Any]
    previous_hash: str
    hash_value: str


@dataclass
class AuditLedger:
    """Small hash chain for traceability, not truth or authorship attestation.

    The public records property exposes the live ledger so callers can mutate it
    intentionally in tests and code paths that need to simulate tampering. Use the
    snapshot() method when a defensive copy is required.
    """

    _records: list[AuditRecord] = field(default_factory=list, repr=False)

    @property
    def records(self) -> list[AuditRecord]:
        """Return the live ledger list.

        This intentionally preserves the ability to tamper with or clear the ledger
        in order to validate mutation-detection logic. A defensive snapshot is
        available via snapshot().
        """
        return self._records

    def snapshot(self) -> list[AuditRecord]:
        """Return a deep-copied snapshot of the current ledger."""
        return copy.deepcopy(self._records)

    @property
    def head_hash(self) -> str:
        """Return the current chain head, or GENESIS for an empty ledger."""
        return self._records[-1].hash_value if self._records else "GENESIS"

    def commit(self, payload: Mapping[str, Any]) -> AuditRecord:
        previous_hash = self.head_hash
        index = len(self._records)
        stored_payload = copy.deepcopy(dict(payload))
        normalized = _canonical_payload(stored_payload)
        digest = hashlib.sha256(f"{index}:{previous_hash}:{normalized}".encode("utf-8")).hexdigest()
        record = AuditRecord(
            index=index,
            payload=stored_payload,
            previous_hash=previous_hash,
            hash_value=f"sha256:{digest}",
        )
        self._records.append(record)
        return copy.deepcopy(record)

    def verify(self, *, expected_head_hash: str | None = None) -> bool:
        """Verify chain structure/content, optionally against a trusted checkpoint."""
        previous_hash = "GENESIS"
        for index, record in enumerate(self._records):
            if record.index != index or record.previous_hash != previous_hash:
                return False
            try:
                normalized = _canonical_payload(record.payload)
            except (TypeError, ValueError):
                return False
            digest = hashlib.sha256(f"{index}:{previous_hash}:{normalized}".encode("utf-8")).hexdigest()
            if record.hash_value != f"sha256:{digest}":
                return False
            previous_hash = record.hash_value
        if expected_head_hash is not None and previous_hash != expected_head_hash:
            return False
        return True

    def rollback_last(self, expected_hash: str) -> AuditRecord:
        """Remove only the current tail when its hash is explicitly acknowledged."""
        if not self._records:
            raise ValueError("audit ledger is empty")
        current = self._records[-1]
        if current.hash_value != expected_hash:
            raise ValueError("audit rollback hash does not match the current ledger tail")
        return copy.deepcopy(self._records.pop())


def _canonical_payload(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
