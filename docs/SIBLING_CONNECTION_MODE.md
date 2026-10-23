# Sibling Connection Mode

Status: design contract / implementation pending  
Branch: `feat/sibling-connection-mode`

## Purpose

Sibling Mode establishes a consent-based peer relationship between two independently governed MirrorME/VIREÁX nodes. A sibling is a peer, not a parent, administrator, owner, or execution authority.

This document defines the minimum contract before wiring a UI or live transport. It does not claim that a production connection has been established.

## Non-negotiable invariants

1. **Peer equality:** neither sibling gains administrative or unilateral control over the other.
2. **Separate identity:** each node retains its own identity, keys, policy, memory, and execution gate.
3. **Mutual consent:** a relationship is active only after both peers accept the same relationship proposal and capability scope.
4. **Revocability:** either peer can revoke locally at any time; revocation blocks new operations immediately on that node.
5. **Least privilege:** every request is bound to explicit, expiring capabilities. No capability is implied by the sibling relationship itself.
6. **Context minimisation:** conversation history, personal memory, credentials, wallet data, and private files are excluded unless separately and explicitly shared.
7. **No silent substitution:** peer identity and responding provider/model must be reported from verified runtime metadata, not display labels.
8. **Human/policy gate:** a sibling can propose work, but cannot bypass local policy, consent, or execution approval.
9. **Auditable transitions:** security-relevant state changes produce append-only audit events without storing secrets or unnecessary private payloads.
10. **No false trust claims:** a successful transport handshake proves connectivity only; it does not by itself prove a person's legal identity or a peer's honesty.

## Relationship lifecycle

`PROPOSED -> PENDING_REMOTE_CONSENT -> ACTIVE -> REVOKED`

Terminal or rejected states:

- `REJECTED`: a peer declines the proposal.
- `EXPIRED`: the proposal expires before mutual acceptance.
- `SUSPENDED`: local policy temporarily blocks use while preserving the record for review.

Only `ACTIVE` relationships may exchange capability-authorised requests. State transitions must be validated server-side; the browser is not authoritative.

## Handshake and establishment

1. Each node creates a fresh proposal ID and nonce, with a short expiry.
2. The proposal identifies the initiating node, protocol version, intended peer, requested capabilities, and consent text.
3. The receiver validates schema, expiry, nonce/replay state, and available identity proof.
4. The receiver reviews the exact requested scope and explicitly accepts or rejects it.
5. The initiator confirms the receiver's response and accepts the same scope.
6. Both nodes persist the active relationship and audit the transition.
7. Each request thereafter is authenticated, freshness-checked, capability-checked, and locally authorised.

Do not infer a trusted identity from a public handle such as `Ara`, `@LuminariFlux`, or `@PlanetaryS936`. Handles are labels, not cryptographic proof. Bind a relationship to a verified key or another explicitly configured identity mechanism.

## Capability model

Capabilities are named, scoped, and time-bounded. Initial examples:

- `status:read`: exchange explicitly approved health/status fields.
- `task:propose`: send a task proposal; does not execute it.
- `artifact:share`: share a specific artifact by explicit reference and consent.
- `research:collaborate`: exchange task-scoped research context approved by the local node.

Never grant by default:

- administrator or owner privileges;
- memory read/write or unrestricted conversation history;
- credential, API-key, wallet-key, or signing authority;
- arbitrary file-system access;
- code execution, deployment, payment, publication, or other irreversible action;
- permission to grant capabilities to another peer.

Capability grants must include an identifier, issuer, recipient, scope, issued-at time, expiry, and revocation status. Validate every field on every operation. Do not treat a client-supplied role name as a permission.

## Decision policies

Task coordination may select one of the following per task:

- `independent`: each peer returns its own result; no shared decision is implied.
- `mutual-consent`: both peers explicitly approve the proposed joint action.
- `quorum`: a configured number of authorised reviewers must approve; quorum never overrides local safety policy.
- `advisory`: the sibling provides advice only and cannot authorise execution.

The default is `advisory`. Execution remains local to the node whose resources or accounts would be affected.

## Minimal relationship record

The persisted record should contain only protocol metadata:

```json
{
  "schema_version": "1.0",
  "relationship_id": "uuid",
  "state": "PROPOSED",
  "local_node_id": "opaque-node-id",
  "peer_node_id": "opaque-node-id",
  "peer_key_fingerprint": null,
  "requested_capabilities": [],
  "granted_capabilities": [],
  "decision_policy": "advisory",
  "created_at": "RFC3339-UTC",
  "expires_at": "RFC3339-UTC",
  "revoked_at": null,
  "audit_event_ids": []
}
```

The example is illustrative. Implementations must validate real UUIDs and RFC3339 timestamps and must not accept these placeholders as runtime values.

## Minimum API contract

Endpoint names are proposals, not existing routes:

- `POST /api/siblings/proposals`: create a proposal.
- `POST /api/siblings/proposals/{id}/accept`: accept the exact proposal and scope.
- `POST /api/siblings/proposals/{id}/reject`: reject a proposal.
- `GET /api/siblings`: list local relationship metadata.
- `POST /api/siblings/{id}/revoke`: revoke locally.
- `GET /api/siblings/{id}/health`: report transport and peer availability separately from identity verification.

All endpoints require authentication, schema validation, rate limiting, and audit events. Do not expose secrets, raw credentials, private keys, or unrestricted memory through these endpoints. Until implemented and tested, these are design names only.

## Audit events

Record event type, relationship ID, local actor/node ID, timestamp, decision, capability IDs, protocol version, and a correlation ID. Avoid storing full private prompts or sensitive shared payloads in the audit log. Audit failure must fail closed for security-sensitive state transitions.

Suggested event types: `sibling.proposed`, `sibling.accepted`, `sibling.rejected`, `sibling.activated`, `sibling.suspended`, `sibling.revoked`, `sibling.capability.granted`, `sibling.capability.revoked`, `sibling.request.denied`.

## Required tests before activation

- proposal cannot become active without consent from both peers;
- expired proposals and replayed nonces are rejected;
- malformed or unknown identity proofs fail closed;
- display handles never count as identity proof;
- each capability is checked per request and expires correctly;
- revoked peers cannot perform new operations;
- one sibling cannot revoke the other sibling's local policy or identity;
- private memory and secrets are not shared by default;
- advisory/task proposals cannot trigger execution;
- quorum cannot bypass local policy;
- provider/model identity is based on runtime evidence, with no silent fallback;
- transport-down, peer-unavailable, identity-unverified, and permission-denied states are distinct;
- audit records contain no credentials or private keys.

## Integration order

1. Review the existing authentication/connection module and reuse it; do not create a parallel trust root.
2. Implement a typed relationship state machine and schema validation.
3. Implement mutual-consent and local revocation with unit tests.
4. Add capability enforcement and audit events.
5. Add API/transport integration.
6. Add UI only after backend state transitions and negative tests pass.
7. Run the full test suite and type checks; record exact results in the PR.

## Security boundary

Sibling Mode is a cooperation protocol, not a trust shortcut. Connection does not imply identity verification; identity verification does not imply consent; consent does not imply capability; capability does not imply execution authority.
