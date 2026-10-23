from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
import hmac
from typing import Protocol

from .models import AccessScope, ResourceEnvelope, ResourceStatus


class Signer(Protocol):
    def sign(self, envelope: ResourceEnvelope) -> ResourceEnvelope: ...

    def verify(self, envelope: ResourceEnvelope) -> bool: ...


class HMACSigner:
    """Development signer.

    Production deployments should replace this with an asymmetric signer backed
    by a node keystore or hardware-protected key. The shared secret must never be
    committed or exposed to the browser.
    """

    def __init__(self, secret: bytes) -> None:
        if len(secret) < 32:
            raise ValueError("signing secret must contain at least 32 bytes")
        self._secret = secret

    def sign(self, envelope: ResourceEnvelope) -> ResourceEnvelope:
        # Sign the envelope exactly as supplied. Callers must finalize all
        # manifest fields before signing; mutating a signed manifest invalidates
        # the signature.
        signature = hmac.new(
            self._secret,
            envelope.canonical_manifest_bytes(),
            sha256,
        ).hexdigest()
        return replace(envelope, signature=f"hmac-sha256:{signature}")

    def verify(self, envelope: ResourceEnvelope) -> bool:
        if not envelope.signature or not envelope.signature.startswith("hmac-sha256:"):
            return False
        expected = hmac.new(
            self._secret,
            envelope.canonical_manifest_bytes(),
            sha256,
        ).hexdigest()
        return hmac.compare_digest(envelope.signature.removeprefix("hmac-sha256:"), expected)


def may_read(envelope: ResourceEnvelope, principal: str) -> bool:
    manifest = envelope.manifest
    if manifest.status is ResourceStatus.REVOKED:
        return False
    if principal == manifest.owner_principal:
        return True
    if principal in manifest.allowed_principals:
        return True
    return manifest.access_scope in {
        AccessScope.PUBLIC,
        AccessScope.COMMUNITY,
        AccessScope.ORGANISATION,
    }


def may_publish(envelope: ResourceEnvelope, principal: str) -> bool:
    return principal == envelope.manifest.owner_principal
