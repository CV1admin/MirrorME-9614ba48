# MirrorME — Civilisation.One Engineering Console

MirrorME is a Vite + React + TypeScript engineering console for the Civilisation.One / MirrorME project.

It provides a local-first interface for simulated telemetry, reasoning workflows, audit panels, and multi-model orchestration experiments through the VIREAX / QVIREAX layer.

---

## What is included

- MirrorME / MKone dashboard layout
- Live simulated telemetry stream
- Vireax stability, drift, and error state handling
- Cognitive Flight Recorder chat panel
- Local/Ollama chat path for private local testing
- Local MirrorME bridge on `http://localhost:8765`
- Static SPA 404 redirect for direct `/mirrorme` page loads
- Gemini browser test path when `VITE_GEMINI_API_KEY` is explicitly configured
- GPT/OpenAI adapter boundary prepared for server-side integration
- Contradiction Trap / logic audit panel
- Civilisation.One dashboard layer
- GitHub Pages deployment workflow

---

## Correct URLs

Local development URL:

```text
http://localhost:3000/#/mirrorme
```

GitHub Pages URL:

```text
https://cv1admin.github.io/MirrorME/#/mirrorme
```

Do not use this direct path as the primary URL:

```text
https://cv1admin.github.io/MirrorME/mirrorme
```

The app uses hash routing. A static `public/404.html` redirect is included so accidental direct `/mirrorme` page loads can be redirected back to the hash route after deployment.

---

## Current architecture

```text
MirrorME UI
  |
  |-- Dashboard telemetry layer
  |-- Cognitive Flight Recorder chat panel
  |-- Contradiction Trap / audit panel
  |-- Civilisation.One dashboard layer
  |
  +-- VIREAX / QVIREAX reasoning layer
        |
        |-- ModelRouter
        |-- AdapterSpec
        |-- StaticAdapter                 # current mock adapter
        |-- future OpenAIAdapter           # GPT backend adapter
        |-- local MirrorME bridge          # localhost:8765
        |-- Local/Ollama adapter           # localhost:11434 through bridge
        |-- audit ledger
        |-- policy gate
```

The current repository already declares GPT as an OpenAI-backed model role inside the VIREAX/QVIREAX path, but the active adapter is still static/mock unless a real backend adapter is added.

Current role map:

```text
GPT      -> architect
Grok     -> critic
Gemini   -> context_analyst
Claude   -> safety_reviewer
DeepSeek -> technical_validator
Llama    -> local_fallback
```

---

## VIREÁX chat

Ask one question; two to four models each answer alone, then review each other's answers. Open `/#/vireax` in the app.

```bash
python scripts/start_vireax.py                 # this computer: http://127.0.0.1:3000/#/vireax
python scripts/start_vireax.py --tailscale     # also from your phone over Tailscale
python scripts/start_vireax.py --no-ui         # only the bridge, for the hosted site
```

Add `--vireax-model NAME` (repeatable) for default models and `--cloud-model provider/model` for cloud models; set `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` or `GEMINI_API_KEY` in the same terminal first. Every model receives the versioned VIREÁX Mirror Agent system prompt (`qviraex/vireax/prompts/`).

For a real second opinion, pick models from different families. `mkultra:0.3`, `mkultra:0.4` and `mirrorme` are all built on `qwen3:8b`; the page warns when selected models look like the same base model. Details: [docs/MULTI_MODEL_COMMUNICATION.md](docs/MULTI_MODEL_COMMUNICATION.md#chat-window).

## Local biometric assertion verification

The VIREAX consciousness observer supports an optional local biometric assertion gate. It verifies Ed25519 signatures, node/session/operator binding, UTC timestamps, a short maximum assertion lifetime, configured confidence policy, and one-time nonce/assertion replay protection. The observer does not process camera frames or fingerprints and never adds the template hash to its loop hash or public state signal.

The biometric matcher and its liveness detector must run locally and sign the canonical assertion payload only after their own checks pass. This gate does not prove legal identity or guarantee liveness; matcher accuracy and spoof resistance require separate hardware- and threat-model-specific evaluation. Assertion revocation is in-memory for the observer process; production deployments must persist revocation/consumption state securely and manage device-key rotation/revocation.

Install Python runtime dependencies with:

```bash
python -m pip install -r requirements.txt
```

See [Biometric Assertion Security](docs/BIOMETRIC_ASSERTION_SECURITY.md) for the threat model and test requirements.

---

## Local development

Install dependencies:

```bash
npm install
```

Run development server:

```bash
npm run dev
```

Open:

```text
http://localhost:3000/#/mirrorme
```

---

## Connect to local MirrorME

The default local connection path is:

```text
MirrorME browser UI
  -> http://localhost:8765/api/chat
  -> local_bridge/mirrorme_bridge.py
  -> http://localhost:11434/api/chat
  -> Ollama local model
```

Start Ollama:

```bash
ollama serve
```

Build the canonical MirrorME persona on Qwen 3:

```bash
ollama pull qwen3:8b
ollama create mirrorme:latest -f ollama/Modelfile
```

The Modelfile embeds the MirrorME manifesto as canonical persona identity. Its epistemic discipline still distinguishes internal framework axioms from externally established empirical claims.

Start the MirrorME local bridge directly:

```bash
python local_bridge/mirrorme_bridge.py --model mirrorme:latest
```

Or use the startup scripts:

```powershell
./scripts/start-mirrorme.ps1
```

```bash
sh scripts/start-mirrorme.sh
```

Windows troubleshooting for missing GitHub CLI or publishing setup:

```powershell
winget install --id GitHub.cli -e
where.exe gh
gh --version
gh auth login
```

Check bridge health:

```bash
curl http://localhost:8765/health
```

Start the UI:

```bash
npm run dev
```

Open:

```text
http://localhost:3000/#/mirrorme
```

The chat service now defaults to the local bridge:

```text
provider: ollama
endpoint: http://localhost:8765
model: mirrorme:latest
```

Full guide:

```text
docs/LOCAL_MIRRORME_CONNECT.md
```

---

## Checks and production build

Run type checks:

```bash
npm run typecheck
```

Build production output:

```bash
npm run build
```

Run both:

```bash
npm run check
```

Preview production build:

```bash
npm run preview
```

---

## Environment setup

Copy `.env.example` to `.env.local` for local development:

```bash
cp .env.example .env.local
```

Environment variables:

```text
VITE_GEMINI_API_KEY=
OPENAI_API_KEY=
```

### Security boundary

- `VITE_GEMINI_API_KEY` is browser-visible because Vite exposes variables prefixed with `VITE_`.
- `VITE_GEMINI_API_KEY` is suitable only for local/demo browser testing.
- `OPENAI_API_KEY` is server-only.
- Local MirrorME/Ollama mode does not require a cloud API key.
- Never expose `OPENAI_API_KEY` in Vite client code.
- Never commit `.env`, `.env.local`, API keys, private tokens, or credentials.

---

## GPT / OpenAI integration plan

### Current state

GPT is already registered conceptually in the QVIREAX runner:

```python
AdapterSpec(model="GPT", provider="OpenAI", role="architect")
```

At the moment, the active response path uses `StaticAdapter`, so GPT is not yet making a live OpenAI API call.

Current behavior:

```text
input task -> ModelRouter -> StaticAdapter -> mock AdapterResult
```

Target behavior:

```text
input task -> ModelRouter -> OpenAIAdapter -> OpenAI API -> AdapterResult
```

### Required backend adapter

Create a server/local-only adapter such as:

```text
qviraex/vireax/openai_adapter.py
```

The adapter should:

- read `OPENAI_API_KEY` from the server/local environment
- never expose the key to browser code
- accept an `AdapterEnvelope`
- send the prompt and role metadata to OpenAI
- return a normal `AdapterResult`
- log model, provider, role, and audit metadata
- never log secrets

Recommended adapter shape:

```python
from __future__ import annotations

import os

from openai import OpenAI

from .adapters import AdapterEnvelope, AdapterResult, AdapterSpec


class OpenAIAdapter:
    def __init__(self, spec: AdapterSpec, model_name: str = "gpt-4.1-mini") -> None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")

        self.spec = spec
        self.model_name = model_name
        self.client = OpenAI(api_key=api_key)

    def respond(self, envelope: AdapterEnvelope) -> AdapterResult:
        system_message = (
            "You are the GPT architect model inside the MirrorME/VIREAX reasoning stack. "
            "Separate facts, assumptions, hypotheses, and implementation steps. "
            "Do not fabricate sources or claim unsupported tool access."
        )

        response = self.client.responses.create(
            model=self.model_name,
            input=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": envelope.prompt},
            ],
        )

        output = response.output_text

        return AdapterResult(
            model=self.spec.model,
            provider=self.spec.provider,
            role=envelope.role,
            output=output,
            confidence=0.80,
            metadata={
                "backend_model": self.model_name,
                "session_id": envelope.metadata.get("session_id"),
                "operator": envelope.metadata.get("operator"),
            },
        )
```

Then replace the static GPT adapter registration with the real adapter only in a trusted backend/local runtime.

Example:

```python
from qviraex.vireax.adapters import AdapterSpec, StaticAdapter
from qviraex.vireax.openai_adapter import OpenAIAdapter

router.register(
    OpenAIAdapter(
        AdapterSpec(model="GPT", provider="OpenAI", role="architect")
    )
)

router.register(
    StaticAdapter(AdapterSpec(model="Claude", provider="Anthropic", role="safety_reviewer"))
)
router.register(
    StaticAdapter(AdapterSpec(model="Llama", provider="Meta", role="local_fallback"))
)
```

---

## Local/Ollama path

For private local testing, keep the local model route separate from cloud GPT.

Recommended routing:

```text
GPT/OpenAI      -> backend only, API key required
Llama/Ollama    -> local fallback, no cloud dependency
Gemini browser  -> demo/local browser path only
StaticAdapter   -> tests, smoke checks, offline mock runs
```

This separation prevents accidental secret exposure and keeps MirrorME operational when cloud models are unavailable.

---

## Running QVIREAX demo

If the Python package path is configured, run:

```bash
python -m qviraex
```

Expected current behavior:

```text
QVIREAX online
MRQL ritual: demo v0.1
VIREAX state: FINAL_OUTPUT
Next action: COMMIT_AUDIT
Audit hash: sha256:...
```

Because the current adapter is static, this validates routing and audit flow, not live GPT reasoning.

---

## GitHub Pages deployment

The repository includes:

```text
.github/workflows/deploy-pages.yml
```

The workflow builds the Vite app and publishes the `dist` directory to GitHub Pages on every push to `main`.

Expected public URL after Pages is enabled:

```text
https://cv1admin.github.io/MirrorME/#/mirrorme
```

In GitHub repository settings, set:

```text
Settings -> Pages -> Source -> GitHub Actions
```

---

## Runtime note

This public deployment is static. It does not include a backend database, persistent private memory, or verified hardware telemetry.

Dashboard telemetry is generated client-side and must be treated as simulated unless connected to verified instrumentation.

---

## Safety boundary

- Do not paste secrets into chat.
- Do not commit `.env`, `.env.local`, `node_modules`, `.next`, `dist`, or `build`.
- Do not treat simulated telemetry as biological or hardware measurement.
- Do not treat static adapter output as a real model response.
- Declared metrics are hypotheses until connected to verified instrumentation.
- GPT/OpenAI access must run through a backend or trusted local runtime only.
- Local MirrorME bridge must stay bound to localhost unless explicitly secured.
- The local handshake is a runtime readiness check, not cryptographic authentication.
- Persistent memory remains disabled until explicit consent, retention, and deletion rules are implemented.

---

## Project status

```text
MirrorME UI:              active
VIREAX router:            active
Static model adapters:    active
GPT role declaration:     active
Live GPT/OpenAI adapter:  pending
Local MirrorME bridge:    active
Local/Ollama route:       active through localhost:8765
Static 404 redirect:      active after deployment
Persistent memory:        not included in static public deployment
Verified telemetry:       not included in static public deployment
```


---

## Civilisation.One / MKone routing boundary

MirrorME is the member-facing application layer. It must not call the private MKone scientific engine directly.

```text
MirrorME client
  -> authenticated Civilisation.One Global Intelligence Router
  -> policy, consent, provenance and audit gates
  -> private MKone scientific engine
  -> validation report
  -> Admin manual review
  -> optional publication
```

Scientific claims use the MKdataONE status classes: established `[E]`, conditional `[C]`, definition `[D]`, phenomenological `[P]`, hypothesis `[H]`, and deprecated `[X]`. Automated processing cannot promote an `[H]` or `[P]` claim to `[E]`.

See `docs/SYSTEM_REWIRE.md` for the trust boundaries, request envelope, and publication state machine.


## VIREÁX full-stack integration

See [docs/VIREAX_AGENT_INTEGRATION.md](docs/VIREAX_AGENT_INTEGRATION.md) for the reflection/criticism/verification contract, consented-memory state machine, security gates, repository boundaries, and production-readiness requirements. This is a specification and integration plan; it does not imply that all planned capabilities are implemented.
