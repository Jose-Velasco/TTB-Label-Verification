# TTB Label Verification

An AI-powered alcohol label compliance verification tool for TTB (Alcohol and Tobacco Tax and Trade Bureau) compliance agents. Upload label images; a vision AI model extracts fields and compares them against application data, returning per-field pass/fail/warning/unreadable status.

---

## What It Does

1. **Upload** a label image (JPEG, PNG, or WebP, max 10 MB) — or use camera capture
2. **Enter** the seven required TTB application fields
3. **Verify** — the AI model extracts each field from the image and fuzzy-matches against the submitted data
4. **Review** per-field results with an overall `approved` / `rejected` / `needs_review` verdict

Batch mode accepts up to 20 images simultaneously and streams results as each label completes (NDJSON).

---

## Architecture

### Ports & Adapters (Hexagonal)

The vision model provider is swapped via a single environment variable — **zero code changes** required to switch from Ollama (local dev) to Gemini (production):

```
Routes → VerificationService → VisionProvider (Protocol)
                                      ↓
                            LiteLLMVisionAdapter
                                      ↓
                         LiteLLM → Ollama / Gemini / OpenAI
```

- **`VisionProvider`** is a Python `Protocol` (structural subtyping) — the service layer depends on an interface, not a concrete implementation. This is the Ports & Adapters "port."
- **`LiteLLMVisionAdapter`** is the single concrete "adapter." Swapping to a new provider means writing a new adapter class and wiring it in `main.py`'s lifespan — nothing else changes.

### Key Technology Choices

| Choice | Reason |
|--------|--------|
| **LiteLLM** | Unified interface for Ollama, Gemini, OpenAI, Anthropic, and 100+ more. No provider-specific SDK code anywhere. |
| **aiolimiter** | Proactive rate limiting — acquires a token *before* each API call, preventing 429s rather than reacting to them. |
| **tenacity** | Automatic retry with random exponential backoff on `RateLimitError` and `ServiceUnavailableError`. Prevents thundering-herd during large batch runs. |
| **UV** | Fast Python package management with lockfile support; `uv sync --frozen` in Docker ensures reproducible builds. |
| **FastAPI + async throughout** | Allows concurrent batch processing without blocking threads; NDJSON streaming is native. |
| **Pydantic Settings** | All config from environment variables with type validation; no hardcoded values anywhere. |
| **Angular 22 (standalone)** | Standalone components (no NgModules), functional guards, Reactive Forms, lazy-loaded routes, RxJS Observable NDJSON streaming. |

### Government Warning Exact Match

The TTB canonical warning is hardcoded in `backend/app/constants.py`. The validation logic (`services/validation.py`) performs a **strict exact-match** after stripping leading/trailing whitespace. The `GOVERNMENT WARNING:` prefix **must** be ALL CAPS — any deviation (title case, truncation, altered wording) is an immediate `fail`.

All other seven fields use **fuzzy matching** via the LLM prompt — minor differences in capitalization, spacing, abbreviations, or unit formatting are treated as `pass`.

---

## Dev Setup

Two options: **Dev Container** (recommended — zero local tooling needed) or **Docker Compose** (if you prefer managing services manually).

---

### Option A — Dev Container in VS Code (recommended)

Everything runs inside a container. No Python, Node, or UV needed on your machine.

**Prerequisites**

- [VS Code](https://code.visualstudio.com/)
- [Dev Containers extension](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers) (`ms-vscode-remote.remote-containers`)
- Docker Desktop with Compose v2
- 8 GB RAM available (Ollama + gemma3:4b)

**Steps**

1. Open the repo folder in VS Code
2. When prompted _"Reopen in Container"_, click it — or run **Dev Containers: Reopen in Container** from the Command Palette (`Ctrl+Shift+P`)
3. VS Code builds the container image and runs `post-create.sh`, which installs all Python and Node dependencies. This takes a few minutes the first time.
4. Ollama starts as a sidecar and pulls `gemma3:4b` (~3 GB) in the background
5. Launch the dev servers: **Terminal → Run Task → `Start: All`** (or `Ctrl+Shift+B`)
6. VS Code auto-opens http://localhost:3000 once the frontend is up

**What's included**

| Feature | Detail |
|---------|--------|
| Python 3.12 + UV | Pre-installed in the container |
| Node 22 + npm | Pre-installed in the container |
| Recommended extensions | Auto-installed (Pylance, ESLint, etc.) |
| Format on save | Black (Python) |
| Pytest integration | Run/debug tests from the Testing sidebar |
| Port forwarding | 4200 (frontend), 8000 (backend), 11434 (Ollama) |
| Debugger | `F5` → `Debug: Backend` to set breakpoints in Python |

**VS Code Tasks** (`Ctrl+Shift+B` or Terminal → Run Task):

| Task | What it does |
|------|-------------|
| `Start: All` | Starts backend + frontend in parallel (default build task) |
| `Start: Backend` | `uvicorn --reload` on port 8000 |
| `Start: Frontend` | `ng serve` on port 4200 |
| `Test: All` | Runs pytest + jest in parallel |
| `Test: Backend` | `uv run pytest tests/ -v --cov=app` |
| `Test: Frontend` | `npm test` (Jest) |

**Rebuild the container** if you change `Dockerfile` or add new deps:
Command Palette → **Dev Containers: Rebuild Container**

---

### Option B — Docker Compose (manual)

**Prerequisites**

- Docker Desktop with Compose v2
- 8 GB RAM available (Ollama + gemma3:4b)

**Start**

```bash
docker compose -f docker-compose.dev.yml up --build
```

On first run Ollama pulls `gemma3:4b` (~3 GB). This takes several minutes. The backend waits for the healthcheck before starting.

- Frontend: http://localhost:4200
- Backend API: http://localhost:8000
- Access key: `dev-access-key-change-me` (from `.env.dev`)

### Hot Reload

Both backend (`uvicorn --reload`) and frontend (`ng serve --poll 500`) support hot reload — edit files and changes are picked up immediately without restarting containers.

### Run Tests Locally

**Backend** (requires Python 3.12 and UV):
```bash
cd backend
uv sync --dev
uv run pytest tests/ -v --cov=app --cov-report=term-missing
```

**Frontend** (requires Node 20):
```bash
cd frontend
npm install
npm test
```

---

## Production Setup

1. Copy the env template:
   ```bash
   cp .env.prod.example .env.prod
   ```

2. Edit `.env.prod`:
   - Set `GEMINI_API_KEY` (get from Google AI Studio)
   - Set `APP_ACCESS_KEY` to a strong random password
   - Set `FRONTEND_URL` to your domain

3. Start:
   ```bash
   docker compose -f docker-compose.prod.yml up --build -d
   ```

Nginx listens on port 80 and proxies:
- `/api/*` → FastAPI backend
- `/` → Angular frontend (served by nginx inside the frontend container)

For HTTPS, add a Certbot/Let's Encrypt container or terminate TLS at a load balancer.

---

## Access Key for Evaluators

The default dev access key is: **`dev-access-key-change-me`**

Navigate to http://localhost:4200, enter this key on the login page.

### Quick Test with Sample Labels

Three sample labels are included in `frontend/public/samples/`:

| File | Expected Outcome |
|------|-----------------|
| `01_stones_throw_pass.svg` | **APPROVED** — all fields match |
| `02_missing_warning_fail.svg` | **REJECTED** — government warning absent |
| `03_title_case_warning_fail.svg` | **REJECTED** — warning uses title case instead of ALL CAPS |

Sample application data for each is in `frontend/public/samples/data.json`. Use the "Sample Labels" section on the single-verify page to load them with one click.

---

## Known Limitations

- **Free tier rate limiting**: Gemini's free tier allows 15 RPM. For batches larger than ~4 labels, aiolimiter + tenacity will queue and retry automatically — this adds latency. This is an intentional architectural trade-off: correctness (no dropped requests) over raw speed. The `RATE_LIMIT_RPM` env var can be raised on a paid tier.

- **Single application data for batch**: The batch endpoint applies one set of application data to all uploaded labels. Labels with different applications should be verified individually.

- **No persistent storage**: Images are processed in memory and discarded immediately after the response. There is no audit log or result history — this is by design for the stateless architecture.

- **Vision model accuracy**: LLM-based extraction is not 100% reliable on low-quality or unusual label images. The `unreadable` and `needs_review` statuses exist specifically for these cases.

---

## Trade-offs & Assumptions

- **Fuzzy matching is delegated to the LLM**: Rather than implementing a custom string similarity library, the prompt instructs the model to apply fuzzy matching semantics. This means "750ml" == "750 mL" without any code-level normalization. The trade-off is that the LLM's interpretation of "fuzzy" may vary slightly; the government warning bypasses this by using backend exact-match.

- **Session auth via cookies, not JWTs**: For a single-team internal tool, an httponly cookie containing the access key is sufficient and simpler than JWT issuance/validation. For a multi-user system, replace with proper identity management.

- **Semaphore = RPM ÷ 4**: The batch semaphore allows `max(1, RATE_LIMIT_RPM // 4)` concurrent inflight calls. At 15 RPM this is 3 concurrent — conservative enough to avoid spikes while keeping latency reasonable. Tune `RATE_LIMIT_RPM` up on a paid tier and the concurrency scales automatically.
