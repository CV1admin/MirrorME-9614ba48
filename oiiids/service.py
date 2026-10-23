from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from .models import ResourceEnvelope, ResourceManifest, ResourcePayload, ResourceStatus
from .security import Signer, may_publish, may_read
from .store import ResourceStore


class ObserverSink(Protocol):
    def record(self, event: dict[str, str]) -> str: ...


class NullObserver:
    def record(self, event: dict[str, str]) -> str:
        return "observer:none"


@dataclass(frozen=True, slots=True)
class ExchangeResult:
    accepted: bool
    code: str
    envelope: ResourceEnvelope | None = None


class ResourceExchangeService:
    def __init__(
        self,
        *,
        store: ResourceStore,
        signer: Signer,
        observer: ObserverSink | None = None,
    ) -> None:
        self._store = store
        self._signer = signer
        self._observer = observer or NullObserver()

    def publish(self, envelope: ResourceEnvelope, *, principal: str) -> ExchangeResult:
        if not envelope.verify_digest():
            return ExchangeResult(False, "digest_mismatch")
        if not may_publish(envelope, principal):
            return ExchangeResult(False, "publish_forbidden")

        # Finalize status before signing because it is part of the signed manifest.
        to_publish = replace(
            envelope,
            manifest=replace(envelope.manifest, status=ResourceStatus.PUBLISHED),
        )
        published = self._signer.sign(to_publish)
        observer_hash = self._observer.record(
            {
                "event": "resource.publish",
                "resource_id": str(published.manifest.resource_id),
                "version": str(published.manifest.version),
                "digest": published.envelope_digest,
                "principal": principal,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        published = replace(published, observer_hash=observer_hash)
        self._store.put(published)
        return ExchangeResult(True, "published", published)

    def read(
        self,
        resource_id: UUID,
        *,
        principal: str,
        version: int | None = None,
    ) -> ExchangeResult:
        envelope = self._store.get(resource_id, version)
        if envelope is None:
            return ExchangeResult(False, "not_found")
        if not envelope.verify_digest() or not self._signer.verify(envelope):
            return ExchangeResult(False, "integrity_failure")
        if not may_read(envelope, principal):
            return ExchangeResult(False, "read_forbidden")
        return ExchangeResult(True, "ok", envelope)

    def create_next_version(
        self,
        previous: ResourceEnvelope,
        payload: ResourcePayload,
        *,
        principal: str,
    ) -> ResourceEnvelope:
        if principal != previous.manifest.owner_principal:
            raise PermissionError("only the owner may create a new version")
        manifest = ResourceManifest.create(
            resource_id=previous.manifest.resource_id,
            version=previous.manifest.version + 1,
            resource_type=previous.manifest.resource_type,
            creator_node_id=previous.manifest.creator_node_id,
            owner_principal=previous.manifest.owner_principal,
            access_scope=previous.manifest.access_scope,
            parent_digest=previous.envelope_digest,
            citations=previous.manifest.citations,
            allowed_principals=previous.manifest.allowed_principals,
        )
        return ResourceEnvelope.create(manifest, payload)
