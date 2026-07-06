# TTB Label Verification

AI-powered alcohol label compliance verification for TTB compliance agents. Upload or photograph a label, compare it against submitted application data, get a pass/fail per field.

**Live demo:** _[url]_
**Repo:** _[url]_

---

## Setup

Requirements: Docker + Docker Compose, an OpenAI API key.

```bash
git clone <repo-url>
cd ttb-label-verification
cp backend/.env.dev.example backend/.env.dev   # add OPENAI_API_KEY
docker compose -f .devcontainer/docker-compose.devcontainer.yml up
```

- Frontend: `http://localhost:4200`
- Backend: `http://localhost:8000` (`/docs` for API reference)

```bash
# tests
cd backend && uv sync --extra dev && uv run pytest
cd frontend && npm install && npm test
```

A local Ollama/Gemma backend is also available for dev use (no external API dependency) — see [Local model backend](#local-model-backend). Not used in the deployed demo.

---

## What it does

**Single verify** — upload a label image or capture one with a camera. Camera capture auto-fills the application-data form by reading the label (flagged as unconfirmed until the agent reviews/edits each field — see [Camera auto-fill](#camera-auto-fill)). Submit to get a per-field pass/fail/warning/unreadable result.

**Batch verify** — upload many label images, each with its own application data (manual entry or CSV import matched by filename). Results stream in as each label completes. Triage view: live summary counts, problem labels sorted to the top, click to expand full detail.

**Stress test** — generates a configurable batch (up to 100) of realistic synthetic labels and runs them through the real verification pipeline, scoring results against known ground truth. Useful for validating changes and demonstrating batch behavior at volume.

---

## Approach

Two-step verification per label: a vision model extracts the seven required fields from the image, then each field is judged either by the model (six fields, by meaning) or deterministically in backend code (the government warning, exact string match). The model's opinion never decides pass/fail on the warning — only the exact-match does.

Batch and single-verify share the same underlying verification call; batch is a bounded-concurrency, streaming wrapper around it, not a separate implementation.

---

## Requirement traceability

| Requirement | Status |
|---|---|
| Format-tolerant matching (Dave) | ✅ Six fields judged by meaning, not string equality |
| Exact warning text, word-for-word (Jenny) | ✅ Deterministic exact-match, not model judgment |
| Warning prefix in ALL CAPS (Jenny's specific example) | ✅ Same exact-match; verified against a title-case test case |
| Warning prefix in bold (Jenny) | ⚠️ Soft signal only — see [limitations](#known-limitations) |
| Handle imperfect images (Jenny) | ✅ Tested against blur/rotation/compression/contrast; model flags low confidence rather than guessing |
| ~5 second response (Sarah) | ❌ Not achieved — see [Latency](#latency) |
| Batch upload, 200–300 labels (Sarah/Janet) | ✅ Concurrent, streaming, per-image data; tested at 100 real labels |
| Simple UI for low-tech-comfort users (Sarah) | ✅ Triage-first batch view |
| No COLA integration (Marcus) | ✅ Out of scope, as specified |
| Firewall / no cloud dependency (Marcus) | ⚠️ Real trade-off — see [Local vs. hosted models](#local-vs-hosted-models) |

---

## Key technical decisions

| Decision | Why |
|---|---|
| **Deterministic exact-match for the government warning**, not model judgment | The model is unreliable at self-grading exactness; a hardcoded string comparison against the canonical 27 CFR §16.21 text is not. Verified: the same correct warning passes when transcribed perfectly and fails on a one-character transcription slip — confirming the check is genuinely strict, not fuzzy. |
| **gpt-4o-mini as default model**, not gpt-4o or gpt-5.4-mini | Cheapest option. Benchmarked against both alternatives specifically on warning-transcription reliability: gpt-4o was more consistent (6/6 vs. measurable non-determinism on mini) at ~16x the cost; gpt-5.4-mini performed worse than both. Mini's occasional transcription noise is a documented, accepted trade-off — see [limitations](#known-limitations). |
| **Bold-check as a soft signal**, not a hard gate | Bold is a visual attribute a text-extraction pipeline can't reliably verify. The model reports a yes/no/uncertain judgment that can contribute to a "needs review" flag but never causes a hard rejection alone, to avoid false-rejecting compliant labels on a shaky visual call. |
| **Batch: per-image application data**, not one shared form | Real scenario is many *different* products submitted at once (large importers), not many copies of one label. CSV import matches rows to images by filename. |
| **Batch: bounded concurrency sized to TPM, not RPM** | Actual OpenAI constraint is tokens-per-minute — at ~30-40k tokens/label, TPM is the binding limit well before request-count limits are. |
| **OpenAI Batch API rejected** | 50% cheaper but 1-6hr async turnaround; incompatible with the interactive, streaming UX this tool needs. |
| **Local Ollama backend kept as an alternative, not deployed** | No GPU on the deploy host; CPU inference is too slow to be usable. Kept for the firewall-restricted, no-external-API scenario Marcus described — same interface, swappable backend. |

---

## Latency

Sarah's 5-second bar came from a real prior failure (a vendor pilot at 30-40s/label that agents abandoned). Investigated rather than assumed unsolvable:

- Full app stack (auth, rate limiting, retries, image handling), with the network call mocked out: **10.7ms**.
- Real network call, no image, minimal tokens: **~6.5s**.
- Full-size vs. heavily downscaled image, both warm: statistically identical (~6-8s either way).

**Conclusion**: the ~6-8s floor is external (network + OpenAI-side processing) and not reducible by anything in this app. The 5-second target is better served by not blocking on it — batch streams results as each label completes rather than waiting for the slowest one, and the UI shows live progress rather than a bare spinner.

---

## Known limitations

- Government warning bold-check is a probabilistic visual judgment, not guaranteed.
- gpt-4o-mini shows measurable transcription non-determinism on the warning field — same input can occasionally produce a different pass/fail across runs. gpt-4o is more consistent at higher cost.
- Exact-match strictness means a genuinely compliant but poorly-photographed label can fail the warning check and require human review. Deliberate: false-reject is the safer default for this field.
- `OPENAI_IMAGE_DETAIL=low` was only validated on clean synthetic labels, not real photographs; `high` is the production default.
- A few pre-existing backend test failures exist on a clean checkout, unrelated to this project's changes (test-suite mocking issues).
- Local Ollama/Gemma backend isn't part of the deployed environment — no GPU on the host.

---

## Camera auto-fill

Auto-filling application data from the same label being verified would make verification circular. Auto-filled fields are marked unconfirmed (visually flagged, banner shown) and only clear once the agent actually edits or confirms them — the human check against the real application record is what makes this non-circular, not the auto-fill itself.

---

## Assumptions

- Standalone prototype, no COLA integration, per Marcus's scoping.
- All test labels are synthetic; no real applicant data used.
- Human review is expected on every result — this tool triages, it doesn't auto-approve.
- A real TTB deployment would likely need the local-model path given the firewall constraint described; this app's OpenAI/Ollama backends share one interface specifically to keep that option open.

---

## Deployment

Frontend and backend served from a single origin (Angular static build + FastAPI behind one nginx instance) to avoid cross-origin auth complications. Only the OpenAI backend is deployed. See `docker-compose.prod.yml` (repo root) plus `deploy/` for the nginx config, TLS/certbot setup, and full deployment guide.

---

## Local model backend

Set `VISION_MODEL` in `.env.dev` to switch to the local Ollama/Gemma path (see `.env.dev.example`). Requires a local GPU for usable performance; dev-only.
