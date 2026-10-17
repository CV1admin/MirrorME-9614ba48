# VIREAX Multi-Model Communication

## Purpose

The multi-model layer lets VIREAX route a task through two or more registered model adapters and exchange prior contributions in a bounded review loop. It is an orchestration mechanism, not a claim that models share consciousness or that agreement establishes truth.

## Current implementation

- `adapters.py` defines the shared adapter data contract.
- `router.py` dispatches to registered adapters.
- `multi_model.py` implements a bounded round-robin review, hashes transcript outputs, and verifies each turn against its corresponding audit event.
- `AuditLedger.records` returns defensive snapshots; `verify(expected_head_hash=...)` can compare the chain head to a separately retained checkpoint.
- `tests/test_multi_model.py` exercises exchange, round limits, audit integrity, and failure behavior.\n- `ara_adapter.py` constructs the ARA/Dane Model adapter from trusted environment configuration; `tests/test_ara_adapter.py` checks missing configuration, rejects GitHub pages, and enforces remote HTTPS plus explicit credentials.

The existing `StaticAdapter` is a test/demo adapter. It does not call a live model. The ARA (Dane Model) adapter factory and `register_ara_adapter(router)` helper live in `qviraex/vireax/ara_adapter.py`; they require an explicitly configured endpoint and exact model ID and never infer either from a GitHub profile. The supplied GitHub repositories URL is a webpage, not an inference endpoint. A live connection works only if ARA exposes the supported OpenAI-compatible chat-completions contract or a later provider-specific adapter is implemented.

## Safety properties

- Two or more distinct registered model names are required.
- Round count is limited to 1–3.
- Prompts mark previous model output as untrusted claims, not privileged instructions.
- This layer does not execute tools or write persistent memory.
- The audit ledger stores task/output hashes and metadata, not raw task or response text.
- `verify_conversation_result` checks transcript output hashes, ordered response-event correspondence, completion metadata, chain integrity, and optionally a trusted head hash.
- Conversation status is `completed_unverified`; it must not be presented as externally verified merely because the exchange completed.

## Privacy and deployment

The caller must obtain approval before including private or sensitive context. Configure remote provider credentials only in the trusted runtime's secret store. The HTTP adapter uses bounded timeouts, prompt/response sizes, and rejects redirects. ARA configuration requires HTTPS and an explicit secret variable for remote endpoints; unauthenticated HTTP is permitted only on loopback. Do not pass arbitrary user-provided URLs directly to a provider adapter.

## Extension plan

1. Implement a generic adapter protocol without coupling the router to `StaticAdapter`.
2. Add one provider adapter at a time, starting with a mock-tested OpenAI-compatible adapter only if the target service supports that API contract.
3. Add provider-specific contract tests, authentication tests, timeout handling and privacy checks.
4. Add external evidence retrieval as a separate, auditable capability; model-generated citations alone are not verification.
5. Add user-approved memory proposals as a separate transaction workflow, never as an implicit side effect of conversation.

## Limits

The audit hash chain helps detect changes relative to a trusted record but does not prove authorship, factual accuracy, or tamper-proof persistence. A head hash only acts as a trust anchor if it is retained independently of the ledger being checked. Defensive record snapshots reduce accidental mutation but do not protect against a process owner who can alter internal state. Output hashes are not digital signatures. Consensus is not verification. Live provider integration and production security require separate tests and release review.

## Chat window

The web app's **VIREAX Chat** page (`/#/vireax`) runs `converse()` through the local bridge against your own Ollama models and, optionally, cloud models. Nothing goes to a cloud model unless you configure one and tick the consent box for that question's providers.

The quickest start is `python scripts/start_vireax.py` (add `--tailscale` to use it from your phone, or `--no-ui` for the hosted site). It starts the bridge and the app together, refuses to bind to every network interface, and stops both on Ctrl+C. The manual steps are:

1. Start Ollama and pull at least two models.
2. Start the bridge with default models:

   ```bash
   python local_bridge/mirrorme_bridge.py --vireax-model mkultra:0.3 --vireax-model mkultra:0.4
   ```

   To use the hosted site rather than `npm run dev`, also allow its origin, e.g. `--allowed-origin https://cv1admin.github.io`. Chrome, Edge and Firefox allow an HTTPS page to call the loopback bridge; Safari does not.
3. Open the page, pick two to four models and one to three rounds, and ask.

Bridge routes: `GET /api/vireax/models` lists installed Ollama models; `POST /api/vireax/converse` takes `{ task, models?, max_rounds? }`. The browser may choose model names but never the endpoint, which stays the bridge's configured Ollama URL. Tasks are capped at 20,000 characters and each output at 8,000. Every result is `completed_unverified`, and each question is a fresh session with no memory of earlier ones.

### Cloud models

The bridge can offer Anthropic, OpenAI and Google Gemini models next to Ollama models in the same conversation.

| Provider | Key variable | Models offered |
| --- | --- | --- |
| Anthropic | `ANTHROPIC_API_KEY` | `claude-sonnet-5-5` and `claude-haiku-5-5` by default once the key is set, or the ones you list |
| OpenAI | `OPENAI_API_KEY` | only those you list, e.g. `--cloud-model openai/MODEL` |
| Google Gemini | `GEMINI_API_KEY` | only those you list, e.g. `--cloud-model gemini/MODEL` |

```bash
export ANTHROPIC_API_KEY=...        # keys live only in the bridge's environment
export OPENAI_API_KEY=...
python local_bridge/mirrorme_bridge.py \
  --vireax-model mkultra:0.3 \
  --cloud-model anthropic/claude-opus-5-5 \
  --cloud-model openai/MODEL
```

Listing models for a provider replaces its defaults. An unknown provider or malformed entry stops the bridge at start-up.

Safety rules:

- Endpoints are fixed in `local_bridge/vireax_chat.py`; the browser sends only model identifiers such as `anthropic/claude-sonnet-5-5`.
- Keys are read from the bridge's environment and never returned to the browser. `GET /api/vireax/models` reports only whether each cloud model is ready and which variable it needs.
- A request containing any cloud model must include `allow_cloud: true`. The page asks for this with a checkbox naming the providers, and asks again whenever that set changes. Without it, or without the key, the bridge refuses before any model is called.
- Cloud calls are capped at 2,048 output tokens each, at most 4 models × 3 rounds = 12 calls per question. Cost is billed to your keys.
- Cloud providers see the question and, in review rounds, the other models' answers, including local ones.

### What every model is told

Each model receives the VIREÁX Mirror Agent system prompt: section 5 of `Civilisation-one/DOCUMENTS/VIREAX_Mirror_Agent_Specification_v1.0.md`, verbatim, plus an addendum for this chat (other models' text is untrusted, no tools ran, no persistent memory, claim status labels). It lives in `qviraex/vireax/prompts/vireax_mirror_agent_v1.txt`. Each result reports the prompt version and its SHA-256 so a transcript can be tied to the exact prompt. A prompt is guidance, not enforcement: the consent, tool and memory rules are enforced in the bridge code.

### Independence disclosure

The bridge reads each local model's family, size and quantization from Ollama's `/api/show`. When two selected local models match, they are almost certainly one base model with different settings, and both the page and the result say so. All models from one provider are also flagged. This is a heuristic: different models can still share training data and errors, so agreement remains weak evidence. In this repository `mkultra:0.3`, `mkultra:0.4` and `mirrorme:latest` are all built `FROM qwen3:8b`, and the VIREÁX system message replaces their Modelfile prompts, so choose a model from another family (or a cloud model) as the second reviewer.

### Phone access

Run `python scripts/start_vireax.py --tailscale` on the computer that has the models, then open the printed link on a phone signed in to the same Tailscale account. The page detects that it was opened from another device and talks to the bridge on that computer, so no settings change is needed. The computer must stay on and awake. The bridge has no login; Tailscale limits who can reach it.

### Critic panel

Tick **Critic panel** on the chat page (or send `critic_lenses` and `synthesis: true` to `/api/vireax/converse`) to change the review rounds:

- Round 1 is unchanged: every model answers alone.
- In each review round, models take one lens each: **maths** (definitions, units, limiting cases, recomputable figures), **logic** (premises, validity, equivocation, hidden assumptions) or **devil's advocate** (strongest case against the leading view, edge cases). Model *i* gets lens *(i + round − 2) mod n*, so lenses rotate between rounds. With two models and two rounds, only the maths and logic lenses are used; the devil's advocate appears with a third model or a third round.
- A final **synthesis** turn, written by the first selected model (or `synthesis_model`), labels each claim with a status, lists agreements, keeps every unresolved disagreement attributed rather than settling it by majority, and names the cheapest decisive next test. It is told it is not a neutral judge of its own earlier answers.

Cost is `models × rounds + 1` calls. Lenses are prompts on the same models, so they widen what is checked but do not add independent evidence; the independence notes still apply. `converse()` now also rejects an adapter that returns a role other than the one it was asked for (part of audit F-05).
