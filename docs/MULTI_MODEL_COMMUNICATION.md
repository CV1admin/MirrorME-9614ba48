# VIREAX Multi-Model Communication

## Purpose

The multi-model layer lets VIREAX route a task through two or more registered model adapters and exchange prior contributions in a bounded review loop. It is an orchestration mechanism, not a claim that models share consciousness or that agreement establishes truth.

## Current implementation

- `adapters.py` defines the shared adapter data contract.
- `router.py` dispatches to registered adapters.
- `multi_model.py` implements a bounded round-robin review and records response hashes in the existing `AuditLedger`.
- `tests/test_multi_model.py` exercises exchange, round limits, audit integrity, and failure behavior.

The existing `StaticAdapter` is a test/demo adapter. It does not call a live model. ARA or any other model must be integrated through a separately configured adapter for its actual runtime/API.

## Safety properties

- Two or more distinct registered model names are required.
- Round count is limited to 1–3.
- Prompts mark previous model output as untrusted claims, not privileged instructions.
- This layer does not execute tools or write persistent memory.
- The audit ledger stores task/output hashes and metadata, not raw task or response text.
- Conversation status is `completed_unverified`; it must not be presented as externally verified merely because the exchange completed.

## Privacy and deployment

The caller must obtain approval before including private or sensitive context. Configure remote provider credentials only in the trusted runtime's secret store. A future HTTP adapter must use HTTPS for non-local endpoints, bounded timeouts and response sizes, safe endpoint allowlisting, and explicit data-sharing controls. Do not pass arbitrary user-provided URLs directly to a provider adapter.

## Extension plan

1. Implement a generic adapter protocol without coupling the router to `StaticAdapter`.
2. Add one provider adapter at a time, starting with a mock-tested OpenAI-compatible adapter only if the target service supports that API contract.
3. Add provider-specific contract tests, authentication tests, timeout handling and privacy checks.
4. Add external evidence retrieval as a separate, auditable capability; model-generated citations alone are not verification.
5. Add user-approved memory proposals as a separate transaction workflow, never as an implicit side effect of conversation.

## Limits

The audit hash chain helps detect changes relative to a trusted record but does not prove authorship, factual accuracy, or tamper-proof persistence. Output hashes are not digital signatures. Consensus is not verification. Live provider integration and production security require separate tests and release review.
