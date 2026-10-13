# VIREAX local biometric assertion security

## Scope

This component accepts a local assertion from a separately implemented biometric matcher. It does not capture or process face, fingerprint, depth, or other biometric samples, and it does not claim sentience or legal identity proof.

## Trust boundary

1. A local matcher performs biometric comparison and liveness detection.
2. The matcher signs the canonical assertion payload using an enrolled Ed25519 device key.
3. `ConsciousnessObserverMode` verifies the signature against its configured trusted public key and validates node, session, operator, timestamps, confidence policy, liveness flag, revocation, and replay state.
4. The observer records only a hash-chain marker containing the assertion ID and method. The template hash is not added to the loop hash or public signal.
5. Checkpoints revalidate the active assertion, including expiry and revocation.

The observer's `liveness_passed` flag is trustworthy only to the extent that the matcher, key custody, and enrollment process are trustworthy. Active challenges, passive depth, texture/moiré, and micro-movement are signals—not universal guarantees. Evaluate the chosen matcher against presentation attacks and injection attacks relevant to the actual device and deployment.

## Assertion format

The signed canonical payload includes every assertion field except `signature`, serialized as UTF-8 JSON with sorted keys, compact separators, Unicode preserved, and non-finite numbers prohibited. Signatures are Base64-encoded Ed25519 signatures over those exact bytes. The public key must be PEM SubjectPublicKeyInfo containing an Ed25519 key.

Assertions bind to the configured node, operator, and session. `issued_at` and `expires_at` must be timezone-aware ISO-8601 timestamps; future issue times, expired assertions, inverted times, and lifetimes over the configured TTL are rejected. Default confidence threshold is 0.8 and default maximum TTL is 300 seconds; deployments should tune these values to validated matcher-specific calibration.

## Privacy and retention

The template hash is potentially linkable biometric-derived metadata even though it is not the template itself. Keep it local to the matcher/observer boundary, never log it, never include it in the loop hash, and do not persist it by default. Raw images, templates, embeddings, and biometric samples must not be placed in the observer, audit ledger, telemetry, or network payloads. Biometric consent must remain separate, explicit, and revocable in the user-facing layer; the existing observer consent gate remains mandatory.

## Replay and revocation limitations

Assertion IDs and nonces are single-use within one observer process. The in-memory consumed/revoked sets are not durable across restarts and are not shared between devices or processes. A production deployment must provide durable, privacy-preserving replay state and a trusted key lifecycle/revocation mechanism. Until then, this implementation is a local prototype gate, not production-ready authentication.

## Verification tests

The automated suite covers valid real signatures, missing assertions, tampering, wrong keys, binding mismatch, liveness failure, confidence thresholds, timestamp/TTL checks, replay, revocation, checkpoint expiry rechecks, and activation rollback. It does not replace independent biometric matcher evaluation, secure device-key storage, penetration testing, or deployment-specific privacy review.
