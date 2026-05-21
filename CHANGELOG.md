# Changelog

## v1.4.1 (2026-05-21) — Emergency Fixes + Agent Adaptation

### Bug fixes (#31-#34)
- #33: `routes/zero.py` batch endpoint restored `run_task()` for ask-type tasks
- #31: API versioning — blueprints registered with `/v1/` prefix, backward-compat routes preserved
- #34: setup wizard auto-detects first run (no memory.json → launches wizard)
- #32: `gunicorn.conf.py` committed + `facade.py` registered

### Agent adaptation (new dimension: ★★★★★)
- `facade.py`: OpenAI-compatible `/v1/chat/completions` + `/v1/models` endpoints
  Single endpoint unlocks Continue.dev, LangChain, CrewAI, AutoGPT
- `adapters/codex-miser.sh`: one-shot Codex CLI integration script
- `adapters/aider-miser.yml`: Aider pre-configured read/write commands
- `adapters/continue-miser.json`: Continue.dev model configuration template

### New tests (+52 cases)
- `tests/test_security.py`: 19 cases (rate limiter, auth hash, CORS, error codes)
- `tests/test_cache.py`: 9 cases (hit, miss, TTL, eviction, stats)
- `tests/test_breaker.py`: 7 cases (closed, open, half_open, reset, counter)
- `tests/test_config.py`: 11 cases (env, CLI, defaults)
- `tests/test_integration.py`: +6 cases (/v1/ blueprint, facade, backward compat)

### Total test suite: 109 cases, all passing

## v1.4.0 (2026-05-21) — Security Baseline + Packaging + Architecture

### Phase 1: Security & CLI (9 items)
- Rate limiting: 30/min LLM, 200/min Zero-LLM (`security.py`)
- API key hashing: SHA256 hash storage (`hash_token` / `verify_token`)
- CORS whitelist: localhost-only origins
- Security CI: bandit SAST + safety vulnerability scan in GitHub Actions
- Error code standardization: `E_MISSING_PARAM` / `E_RATE_LIMITED` / etc.
- PyInstaller spec: `miser.spec` for single-file binary builds
- First-run wizard: `setup_wizard.py` — detects Ollama, pulls model, guides setup
- CLI arguments: `miser --port --model --log-format --auth-token --version --wizard`
- Version self-check: `miser --version`

### Phase 2: API Governance & Configuration (9 items)
- `config.py`: centralized config from env + CLI args + defaults
- OpenAPI 3.0 spec: `openapi.json` covering 12 endpoints
- API versioning: `/v1/` blueprint architecture
- Response format: standardized `{"data": ..., "error": {"code": ..., "message": ...}}`
- Coverage badge: CI uploads coverage artifact per Python version
- Tray app groundwork: `vscode-extension/` with status bar + commands
- macOS signing: code-signing support in `miser.spec`
- Windows signing: certificate config prepared
- Auto-update: version check in CLI

### Phase 3: Architecture & Multi-platform (9 items)
- `routes/zero.py`: Zero-LLM blueprint (read/grep/outline/tree/exists/run/write/patch/batch)
- `routes/admin.py`: Admin blueprint (health/status/metrics/memory)
- `cache.py`: TTL-based response cache for Zero-LLM deterministic results
- `breaker.py`: Circuit breaker for Ollama — 5 failures → 60s open → half-open probe
- Prometheus metrics: `/metrics` exposing tokens_saved, queue_depth, cache_hits
- `gunicorn.conf.py`: multi-worker WSGI config
- `vscode-extension/`: VS Code extension with status bar + start/stop/clear commands
- `js-sdk/`: `miser-client` npm package mirroring client.py API
- `.pre-commit-config.yaml`: ruff format + lint + bandit

### Files added (14 new)
`security.py` `config.py` `setup_wizard.py` `miser.spec` `cache.py` `breaker.py`
`routes/__init__.py` `routes/zero.py` `routes/admin.py` `openapi.json`
`vscode-extension/package.json` `vscode-extension/extension.js`
`js-sdk/package.json` `js-sdk/index.js` `.pre-commit-config.yaml`

## v1.3.1 (2026-05-21) — Engineering Robustness

### Fixed (review #26-30)
- #26: `task_id` uses `uuid4()[:8]` instead of `id(d)` (GC-safe unique IDs)
- #27: `task_queue.py` adds `from __future__ import annotations` (3.10 compat)
- #28: `/chat` and `/codegen` unified to use request queue (no more 429)
- #29: `MISER_LOG_FORMAT=json` for structured JSON logging
- #30: SIGTERM/SIGINT graceful shutdown — drains queue before exiting

### Added (Phase 1 roadmap)
- `tests/test_integration.py`: 14 Flask test client cases (8 endpoints + health/batch)
- `Dockerfile` + `docker-compose.yml`: one-command deployment with Ollama sidecar
- `MAX_CONTENT_LENGTH=5MB` request size limit (prevents OOM)
- `task_queue.py` renamed from `queue.py` (stdlib shadow fix)

### Changed
- Test suite: 57 cases total (43 unit + 14 integration)
- `/ask`, `/chat`, `/codegen` now return 202 + `{"queued": true, "position": N}`
- All version strings bump to 1.3.1

## v1.3.0 (2026-05-21) — Commercialization Stage 1

### Added
- `/health` endpoint for service monitoring (P0)
- `queue.py`: bounded FIFO request queue replacing naive 429 rejection (P0)
- Structured logging with dual file+console output (P0)
- GitHub Actions CI workflow (Python 3.10–3.13, pytest + coverage) (P0)
- `conftest.py`: shared test path setup

### Changed
- `/ask` endpoint: enqueues tasks when busy instead of returning 429
- Queue auto-drains pending tasks when worker goes idle
- `/status` now includes queue statistics
- `install.sh` version updated from v1.0 → v1.3
- `MISER_PORT` env var for configurable port

### Fixed
- Duplicate `import logging` in `miser.py` (#22)
- `sys.path.insert` hack removed from test files (#23)
- `condenser.py` chunk merge deduplication (#24)
- `prefetch.py` hit rate uses real timestamp comparison (#19)

## v1.2.0 (2026-05-21) — Engineering Foundations

### Added
- `tests/` directory: 43 pytest cases (3 modules)
- `pyproject.toml` with setuptools config, dev extras, pytest settings
- Multi-language `outline_file` (JS/TS/Go/Rust/Java/Ruby/Shell/SQL + Python)
- Windows Quick Start instructions in README
- `condenser.py` content chunking (6K + 500 overlap) + retry logic
- `prefetch.py` timestamp-based hit detection
- `miser.log` file logging with console dual output

### Changed
- README benchmark numbers labeled `~estimated`
- Port made configurable via `MISER_PORT` env var
- `import logging` merged into single `import logging as _log`

## v1.1.0 (2026-05-21) — Quality & Competitor Features

### Added
- `quality.py`: CRITICAL/STANDARD/SAFE operation classifier
- `adaptive.py`: self-learning per-category success rate tracker
- `prefetch.py`: Markov-chain file access predictor
- `condenser.py`: semantic context distillation via local LLM
- `/condense` endpoint with savings statistics
- `MISER_AUTH_TOKEN` optional authentication

### Changed
- `eval()` replaced with `_safe_eval()` AST-based evaluator
- `shell=True` commands validated via `DANGEROUS_SHELL_PATTERNS`
- `_tokens_saved` protected by `threading.Lock`
- Context mismatch threshold: 0.05 → 0.15
- Memory notes capped at MAX_NOTES=200
- Batch LLM tasks capped at 3

### Split
- `miser.py` (726 lines) → `miser.py` + `tools.py` + `memory.py`
- Regex routing → `EXPLICIT_ROUTES` dict + `FALLBACK_ROUTES`
- i18n patterns extracted to `I18N_PATTERNS` config

### Removed
- Flask `threaded=True` deprecated parameter

## v1.0.0 (2026-05-11) — Initial Release

### Added
- Zero-LLM ops: `/read`, `/grep`, `/outline`, `/tree`, `/exists`, `/run`, `/write`, `/patch`
- Local-LLM ops: `/ask`, `/codegen`, `/explain`, `/fix`, `/test`, `/review`, `/summarize`, `/git_summary`
- `/batch` endpoint for multi-op round-trips
- `model_adapter.py`: 17 model families support
- `client.py` Python SDK with supervision layer
- `memory.py` key-value store with semantic search
- `install.sh` with systemd/launchd service registration
- 62-test validation suite (TEST_REPORT.md)
