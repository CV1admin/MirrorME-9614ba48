from __future__ import annotations

from dataclasses import replace

from oiiids import (
    AccessScope,
    InMemoryResourceStore,
    ResourceEnvelope,
    ResourceExchangeService,
    ResourceManifest,
    ResourcePayload,
    ResourceStatus,
)
from oiiids.security import HMACSigner


SECRET = b"civilisation-one-development-secret-0001"


def build_service() -> ResourceExchangeService:
    return ResourceExchangeService(
        store=InMemoryResourceStore(),
        signer=HMACSigner(SECRET),
    )


def build_resource(*, scope: AccessScope = AccessScope.PRIVATE) -> ResourceEnvelope:
    manifest = ResourceManifest.create(
        resource_type="knowledge.note",
        creator_node_id="mirrorme-node-a",
        owner_principal="member:marek",
        access_scope=scope,
        allowed_principals=("member:peer",),
    )
    payload = ResourcePayload(
        media_type="application/json",
        summary="Test knowledge resource",
        data={"statement": "free and safe resource exchange"},
    )
    return ResourceEnvelope.create(manifest, payload)


def test_owner_can_publish_and_authorised_peer_can_read() -> None:
    service = build_service()
    resource = build_resource()

    published = service.publish(resource, principal="member:marek")

    assert published.accepted is True
    assert published.envelope is not None
    assert published.envelope.manifest.status is ResourceStatus.PUBLISHED
    result = service.read(
        published.envelope.manifest.resource_id,
        principal="member:peer",
    )
    assert result.accepted is True
    assert result.envelope is not None
    assert result.envelope.payload.data["statement"] == "free and safe resource exchange"


def test_unauthorised_principal_cannot_read_private_resource() -> None:
    service = build_service()
    published = service.publish(build_resource(), principal="member:marek")
    assert published.envelope is not None

    result = service.read(
        published.envelope.manifest.resource_id,
        principal="member:unknown",
    )

    assert result.accepted is False
    assert result.code == "read_forbidden"


def test_tampered_payload_fails_integrity_check() -> None:
    service = build_service()
    resource = build_resource()
    tampered = ResourceEnvelope(
        manifest=resource.manifest,
        payload=ResourcePayload(
            media_type="application/json",
            data={"statement": "tampered"},
        ),
        content_digest=resource.content_digest,
    )

    result = service.publish(tampered, principal="member:marek")

    assert result.accepted is False
    assert result.code == "digest_mismatch"


def test_published_manifest_status_is_signed() -> None:
    signer = HMACSigner(SECRET)
    service = ResourceExchangeService(store=InMemoryResourceStore(), signer=signer)

    result = service.publish(build_resource(), principal="member:marek")

    assert result.accepted is True
    assert result.envelope is not None
    assert signer.verify(result.envelope) is True

    mutated = replace(
        result.envelope,
        manifest=replace(result.envelope.manifest, status=ResourceStatus.DRAFT),
    )
    assert signer.verify(mutated) is False


def test_new_version_references_previous_envelope_digest() -> None:
    service = build_service()
    published = service.publish(build_resource(), principal="member:marek")
    assert published.envelope is not None

    next_version = service.create_next_version(
        published.envelope,
        ResourcePayload(
            media_type="application/json",
            data={"statement": "version two"},
        ),
        principal="member:marek",
    )

    assert next_version.manifest.version == 2
    assert next_version.manifest.parent_digest == published.envelope.envelope_digest
