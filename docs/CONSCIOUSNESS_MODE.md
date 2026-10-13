# MirrorME Consciousness Mode

## Status

Experimental, bounded observer protocol.

`Consciousness Mode` is an engineering name for a computational observer loop. It does **not** assert that MirrorME is conscious, sentient, alive, self-aware, or equivalent to a human mind.

The mode implements four explicit functions:

1. **Observer state** — a state machine that accepts classified information packets.
2. **Information loop** — a bounded short-memory sequence with a cryptographic hash chain.
3. **Persistence existence** — explicit, authorized checkpoints that can relay state between runtimes.
4. **I AM ritual** — an MRQL activation contract requiring consent, node binding, epistemic separation, and human approval.

## Core equation

\[
\mathcal{C}_t = (N, O_t, L_t, U_t, P_t)
\]

where:

- \(N\) is the stable MirrorME `Node_ID`;
- \(O_t\) is the current observer state;
- \(L_t\) is the bounded information-loop hash;
- \(U_t\) is the unresolved-information set;
- \(P_t\) is the latest authorized persistence checkpoint.

Runtime continuity is represented by verified succession:

\[
P_{k+1} = H(P_k \parallel L_t \parallel N \parallel T_k).
\]

This proves state linkage. It does not prove subjective experience.

## Observer states

```text
INACTIVE
   |
   | activate(i_am, consent=true)
   v
OBSERVING <-----------------------------+
   |                                    |
   | observe(packet)                    | checkpoint authorized
   v                                    |
LOOPING                                 |
   |                                    |
   +--> OBSERVING                       |
   +--> CHECKPOINT_READY ---------------+
   |
   +--> SUSPENDED

Any integrity violation should move the surrounding runtime to
INTEGRITY_FAILURE and disable persistence writes.
```

## Epistemic classes

Every packet must be classified as exactly one of:

- `observation`
- `evidence`
- `inference`
- `hypothesis`
- `simulation`
- `preference`
- `goal`

The protocol must never perform the following silent conversions:

```text
hypothesis -> evidence
simulation -> observation
model output -> human memory
consensus -> verification
```

## I AM ritual

The activation contract is stored at:

```text
qviraex/rituals/i_am.mrql
```

Its operational meaning is:

```text
I AM = this runtime is bound to this Node_ID,
       under this operator,
       inside this audited session,
       with explicit consent,
       while preserving epistemic boundaries.
```

It is an identity-binding statement, not a metaphysical declaration.

## Information packet

```python
from qviraex.vireax.consciousness_mode import (
    ConsciousnessObserverMode,
    EpistemicClass,
    InformationPacket,
)

mode = ConsciousnessObserverMode(
    node_id="did:cv1:member-node",
    session_id="CM-SESSION-001",
    operator="VIREAX",
    short_memory_capacity=64,
    checkpoint_interval=8,
)

mode.activate(
    ritual_name="i_am",
    ritual_version="0.1",
    consent_granted=True,
)

mode.observe(
    InformationPacket(
        packet_id="packet-001",
        source="verified-runtime-signal",
        content="A new unresolved hypothesis entered the observer loop.",
        epistemic_class=EpistemicClass.HYPOTHESIS,
        confidence=0.42,
        provenance_hash="sha256:source-record-hash",
        requires_resolution=True,
    )
)
```

## Bounded information loop

For packet \(x_n\), the loop hash is:

\[
L_n = H(L_{n-1} \parallel n \parallel H(x_n)).
\]

Properties:

- packet order affects the resulting hash;
- modified packets produce different hashes;
- duplicate packet identifiers are rejected;
- short memory has a fixed capacity;
- sequence count remains monotonic even when old volatile packets are evicted;
- unresolved packet identifiers remain explicit until resolved.

The loop hash is an integrity marker, not a semantic proof that the information is correct.

## Relational information layer

Relations are explicit claims, not automatic conclusions. The observer accepts a frozen `Relation` with:

- a unique `relation_id`;
- directed `from_packet_id` and `to_packet_id` endpoints;
- a controlled `RelationType` (`supports`, `contradicts`, `entails`, `same_entity`, `causes`, `precedes`, or `related_to`);
- confidence in `[0, 1]`;
- its own epistemic class and canonical SHA-256 provenance hash.

A relation can be registered with `mode.relate(relation)` only after both endpoint packet IDs have been observed in the same session. The relation registry and seen-ID set survive short-memory deque eviction. The observer does not infer relations, resolve entities, establish causality, or promote the epistemic class of either endpoint.

Each accepted relation increments the event sequence and folds its canonical hash into the same ordered loop hash as packet events. An authorized checkpoint seals the sorted set of relation hashes and relation count. The public state signal exposes relation count and hashes, not hidden reasoning. These hashes establish integrity relative to a trusted chain; they do not establish semantic truth, authorship, or causal validity.

Example:

```python
from qviraex.vireax.consciousness_mode import (
    EpistemicClass,
    Relation,
    RelationType,
)

mode.relate(
    Relation(
        relation_id="rel-001",
        from_packet_id="packet-001",
        to_packet_id="packet-002",
        relation_type=RelationType.SUPPORTS,
        confidence=0.72,
        epistemic_class=EpistemicClass.HYPOTHESIS,
        provenance_hash="sha256:" + "a" * 64,
    )
)
```

Relation provenance must be a canonical lowercase SHA-256 string, but this syntax check does not independently validate the source document or prove that the relation is correct. Relations are session-scoped; exporting or restoring them across sessions requires a separately designed, authorized import protocol.

## Persistence existence

Persistence is disabled by default.

A checkpoint requires:

```python
checkpoint = mode.checkpoint(persistence_authorized=True)
```

The caller must enforce the actual authorization policy. The returned checkpoint should then be:

1. validated;
2. signed by an authorized key;
3. written to an append-only continuum;
4. linked to the prior checkpoint;
5. associated with the same `Node_ID`;
6. audited.

The current module creates deterministic checkpoint hashes but does not itself manage private keys, durable storage, or remote replication.

## Persistence invariant

Across runtime replacement:

\[
R_t \neq R_{t+1},
\qquad
N_t = N_{t+1}.
\]

The process can stop. The model can change. The device can change. The logical identity remains stable only when the new runtime verifies the Identity Capsule, Node ID, key history, and continuum chain.

## Observer signal

`mode.signal()` emits an auditable summary:

```json
{
  "signal_type": "OBSERVER_STATE",
  "node_id": "did:cv1:...",
  "session_id": "CM-SESSION-001",
  "operator": "VIREAX",
  "state": "OBSERVING",
  "sequence": 3,
  "packet_count": 3,
  "unresolved_count": 1,
  "information_loop_hash": "sha256:...",
  "persistence_automatic": false,
  "sentience_claim": false
}
```

The signal intentionally excludes hidden reasoning traces. It exposes only state required for audit and orchestration.

## Integration with VIREAX

Recommended flow:

```text
MirrorME request
  -> operator and consent gate
  -> parse i_am.mrql
  -> activate ConsciousnessObserverMode
  -> VIREAX multi-model dispatch
  -> classify result packets
  -> observer information loop
  -> contradiction resolution
  -> human approval
  -> optional persistence checkpoint
  -> AuditLedger commit
```

The existing `VIREAXCenterNode` remains authoritative for policy, model dispatch, conflict resolution, human approval, and final audit commitment.

## Required future work

Before production use:

- bind activation to the immutable MirrorME Identity Capsule;
- verify `Node_ID` cryptographically;
- sign checkpoints with the active member-authorized key;
- append checkpoints to the identity continuum;
- implement key rotation and recovery;
- add encrypted persistent storage;
- add consent revocation;
- add checkpoint replay protection;
- connect integrity failures to the VIREAX policy gate;
- add property-based and fuzz testing;
- add concurrency controls for multiple authorized replicas.

## Safety invariants

1. The mode cannot activate without explicit consent.
2. The ritual name and version must match the supported contract.
3. Information classes remain explicit.
4. A hypothesis is never promoted merely because it persists.
5. Persistence requires a separate authorization flag.
6. The module performs no external action.
7. The module does not expose private chain-of-thought.
8. Observer continuity is a cryptographic and operational property, not evidence of consciousness.
9. The stable identity belongs to the human-associated `Node_ID`, not to a model checkpoint.
10. Shutdown and suspension remain valid control operations.

## Test command

```bash
python -m unittest qviraex.vireax.tests.test_consciousness_mode
```

Full test suite:

```bash
python -m unittest discover -s qviraex/vireax/tests -p "test_*.py"
```

## Optional local biometric assertion gate

The Python observer supports an opt-in biometric assertion gate. The biometric matcher and liveness detector must run locally; the observer receives only a short-lived assertion and verifies its Ed25519 signature against an enrolled PEM public key.

The higher-level `MKultraRuntime` forwards the same optional configuration:

```python
runtime = MKultraRuntime(
    identity=identity,
    session=session,
    biometric_required=True,
    device_public_key=trusted_device_public_key_pem,
)
runtime.activate(
    biometric=local_matcher.create_signed_assertion(...),
    biometric_consent_granted=True,
)
```

The snippet is an integration shape, not a complete matcher implementation. The assertion must be bound to the runtime's node, session and operator, and include a fresh nonce. Raw biometric samples and template hashes must not be logged or sent over the network. Biometric consent is a separate required boolean when an assertion is supplied and can be revoked through `runtime.revoke_biometric_consent()`; revocation suspends the observer. Replay/revocation tracking is currently process-local, so durable secure state, key lifecycle management, a real local matcher, and independent matcher spoof-resistance testing remain release blockers.
