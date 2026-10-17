# VIREÁX Agent — Full-stack integration contract

**Status:** Integration plan, not a claim that every feature is implemented.

## System map

MirrorME / Vite UI
  -> authenticated Civilisation.One WEBSITE API
  -> input schema + origin checks + distributed rate limit
  -> provider adapter (server-side credentials only)
  -> reflection / critic / evidence ledger / verification / synthesis
  -> schema validation + audit metadata
  -> response marked advisory-only and V0 when evidence was not independently checked

Local path (implemented in this repository)

MirrorME `/#/vireax` page
  -> local bridge on the operator's machine (loopback or Tailscale; origin allow-list)
  -> VIREÁX system prompt + bounded multi-model review (qviraex/vireax/multi_model.py)
  -> Ollama models and, with per-question consent, Anthropic / OpenAI / Gemini
  -> hash-audited transcript, status completed_unverified, independence notes

The local path has no user accounts, rate limiter or persistent memory. It is for the operator's own use, not a production deployment.

Approved memory (separate transaction)
  -> propose -> preview exact diff -> user approval -> commit -> audit receipt

## Core behaviour

- Reflect the user's actual argument before evaluating it.
- Keep the original claim, interpretation, assumptions, deductions, empirical evidence, counterarguments, unknowns, and reversal conditions distinct.
- Challenge ideas with specific counterexamples and tests; do not agree by default or reject unconventional ideas by default.
- A model role is not an independent agent. Disclose when several stages use the same provider/model.
- Never invent browsing, source retrieval, calculations, tests, tool calls, or memory.
- Mark outputs as advisory. No stage may execute external actions.

## Required production controls

1. Server-only provider secrets and allow-listed providers/models.
2. Authentication, ownership checks, same-origin POST, bounded input/output, request deadline, per-stage timeout.
3. Distributed rate limiting and provider cost/quota controls; fail closed if required controls are unavailable.
4. Strict structured-output validation and no partial synthesis after required-stage failure.
5. Explicit memory consent tied to the exact previewed content and version.
6. Audit provenance without storing secrets or unnecessary private prompt content.
7. Offline automated tests for validation, injection resistance, rate-limit failure, memory consent, cross-user isolation, and truthful capability labels.
8. Held-out behavioural evaluation and deployment evidence before claiming production readiness.

## Repository boundaries

- Civilisation-one/Modules: normative architecture and epistemic contract.
- CV1admin/MirrorME-9614ba48 (formerly referred to as CV1admin/MirrorME): local UI, adapters, bridge, experimental router and local audit tooling.
- Civilisation-one/WEBSITE: authenticated web workspace, provider-backed reasoning API, collective observation workflow and deployment configuration.

Keep provider credentials out of Vite's VITE_* browser-visible environment. A local bridge is suitable for local testing; it is not a substitute for server-side authentication, distributed rate limiting, or production security review.