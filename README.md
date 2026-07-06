# TTB Label Verification

AI-powered compliance check for alcohol labels. An agent enters the approved application data, uploads or photographs the physical label, and gets a per-field pass/fail/needs-review verdict comparing the two.

**Live demo:** https://labels.jvcodes.dev/login

Access is restricted. **Ask the repo owner for the login if you'd like to try the deployed demo.**

---

## Local Setup

Requires Docker + Docker Compose and an OpenAI API key.

```bash
git clone <repo-url> && cd ttb-label-verification
cp .env.dev.example .env.dev        # add OPENAI_API_KEY
docker compose -f docker-compose.dev.yml up --build
```

Frontend at `http://localhost:4200`, backend at `http://localhost:8000` (`/docs` for the API). A dev container (`.devcontainer/`) is also set up for zero-local-tooling development.

```bash
cd backend && uv sync --extra dev && uv run pytest   # backend tests
cd frontend && npm install && npm test               # frontend tests
```

---

## What it does

- **Single verify** - upload or photograph one label, enter its application data, get a per-field result. Camera capture auto-fills the form from the label (marked unconfirmed until reviewed - see [Camera auto-fill](#camera-auto-fill)).
- **Batch** — many labels, each matched to its own application data by filename (manual entry or CSV import). Results stream in as each completes; a triage view surfaces problem labels first.
    - Sample images and a matching `labels.csv` are in `sample-data/batch/` if you want to try it without preparing your own files.
- **Stress test** - generates synthetic labels and runs them through the real pipeline, scoring against known ground truth. Used to validate changes and demo batch behavior at volume.

---

## Approach

Application data is assumed known - the agent already holds the approved application and is checking whether the label matches it. The app never looks data up (no COLA integration).

Each label is **one model call** that both extracts the fields and compares them to the expected values in a single response - splitting extract and compare into two calls would double latency and cost. Six fields are judged by meaning (so "STONE'S THROW" matches "Stone's Throw"); the government warning is checked by a deterministic exact string-match in backend code against the canonical text, which overrides the model's opinion on that field. Anything the model isn't confident about routes to **needs-review** for a human rather than a silent pass or fail.

Camera capture is the only flow with a second call: an extraction-only pass to auto-fill the form. Batch and stress test reuse the single verify call, wrapped in bounded-concurrency streaming.

---

## Requirement traceability

| Requirement | Status |
|---|---|
| Format-tolerant matching (non-warning fields) | Met - judged by meaning, not string equality |
| Warning exact text, word-for-word + ALL CAPS | Met - deterministic exact-match; verified against a title-case fail case |
| Warning prefix in bold | Met - visual attribute a text pipeline can't guarantee; model verifies |
| Handle imperfect images | Met - tested against blur/rotation/glare/compression; low confidence flags rather than guesses |
| ~5 second response | Met - see [Latency](#latency) |
| Batch upload (200-300 labels) | Met - concurrent, streaming, per-image data; tested at n=50 |
| Simple UI | Met - triage-first batch view |
| Firewall / no cloud dependency | Met - trade-off, see [Assumptions](#assumptions) |

---

## Key decisions

- **Deterministic exact-match for the warning**, not model judgment - the model self-grades exactness unreliably; a hardcoded comparison doesn't. Verified strict, not fuzzy.
- **gpt-4o** - benchmarked against gpt-4o-mini (cheaper but showed transcription non-determinism on the government warning) and gpt-5.4-mini (worse than both). gpt-4o was the most consistent on exact-transcription reliability, which matters most for the one field that's checked by exact string-match.
- **Batch concurrency sized to whichever of RPM or TPM is tighter** - At typical settings (500 RPM / 200k TPM), TPM is the binding limit since each image-heavy request costs far more in tokens than in request count..
- **Local Ollama/Gemma backend kept but not deployed** - same interface, swappable; usable for a firewall-restricted no-external-API scenario, but needs a GPU the deploy host doesn't have.

---

## Latency

Investigated rather than assumed:

- App stack with the network mocked out: **10.7ms** - the app itself isn't the bottleneck.
- Real call: **3.5-4.5s/label** on the deployed path.

 Batch streams each result as it finishes so the UI stays responsive regardless.

---

## Known limitations

- `OPENAI_IMAGE_DETAIL=low` was validated only on clean synthetic labels; `high` can be used for better accuracy, albeit at a higer cost.
- Synthetic stress-test labels are SVG-rendered and degraded programmatically (blur, rotation, compression); they approximate but don't fully replicate real phone-camera conditions (physical glare, true focus blur, uneven lighting).
- No persistent storage or audit log - images and results exist only for the duration of the request/response. There's no history of what was checked, when, or by whom, which a real compliance workflow would likely need.
- Validated end-to-end at n=50 (stress test, avg 4.2s/label) and n=17 (batch via CSV import, avg 3.6s/label). The concurrency logic is sized directly off the OpenAI rate limits.

---

## Camera auto-fill

Auto-filling the form from the same label being verified would be circular. Auto-filled fields are flagged unconfirmed and only clear once edited or confirmed.

---

## Assumptions

- Standalone prototype; no COLA integration, no real applicant data, all test labels synthetic.
- Every result expects human review - the tool triages, it never auto-approves.
- A shared access password suits a small pilot group; a real multi-agency rollout would need identity-backed login instead, for example SSO.
- Agency networks often block outbound calls to external API domains. The hosted deployment sidesteps this - the OpenAI call happens server-side, so agents should use the web URL rather than running locally on a restricted network.

---

## Deployment

Angular build and FastAPI are served from a single origin behind one nginx instance to avoid cross-origin auth complications. Only the OpenAI backend is deployed. See `docker-compose.prod.yml`. Angular build and FastAPI run as two internal-only containers (backend/frontend both bound to 127.0.0.1); a host-level nginx instance (shared with other sites on this server) handles TLS and routes the public subdomain to them.

---

## Project structure

```
backend/
  app/
    main.py              FastAPI entrypoint
    config.py            env-driven settings
    constants.py         canonical warning text, field limits
    adapters/            LiteLLM vision adapter (OpenAI / Ollama)
    prompts/             extract + verify prompt templates
    models/              Pydantic request/response models
    routes/              verify, batch, stress_test, auth
    services/            verification, validation, golden-sample + stress-test generation
    data/samples/        synthetic sample labels + expected data
  tests/                 pytest suite; tests/eval/ is the opt-in real-model suite
  scripts/               offline label/preview generators
  Dockerfile             multi-stage (uv build → slim runtime)
frontend/
  src/app/
    core/                auth guard, interceptor, api/auth/validation services
    features/            login, verify, batch, stress-test pages
    shared/components/   uploaders, camera capture, forms, results, triage table
    models/              typed API models
  nginx.conf             internal static server (port 8080)
  Dockerfile             multi-stage (npm build → nginx runtime)
.devcontainer/           VS Code dev container + local compose
docker-compose.dev.yml   local dev stack
docker-compose.prod.yml  production (backend + frontend; host nginx handles TLS/routing)
```

---

## Local model backend

Set `VISION_MODEL` in `.env.dev` to use the local Ollama/Gemma path (see `.env.dev.example`). Needs a local GPU for usable speed; dev-only.
