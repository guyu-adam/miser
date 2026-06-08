# Miser Bug Tracker

## v1.5.5 — 2026-06-08

### B1: `setup_wizard` module missing → crash on first run
- **Severity:** High (blocks startup on fresh install)
- **Symptom:** `ModuleNotFoundError: No module named 'setup_wizard'`  
- **Cause:** `miser.py` imports `setup_wizard` unconditionally but the module is not in the repo
- **Fix:** Wrapped both `from setup_wizard import wizard` calls in try/except ImportError

### B2: `model="auto"` never resolves to an actual model
- **Severity:** High (LLM endpoints return `(no response)`)
- **Symptom:** `/v1/ask` returns `"(no response)"`, family shows `"default"`, Ollama health shows `"closed"`
- **Cause:** `ModelAdapter("auto")` resolves `detect_family("auto")` → `"default"`, then sends `model="auto"` to Ollama which has no such model. The `backends/` discovery is never used to pick a real model name.
- **Workaround:** Always pass `--model <name>` explicitly (e.g. `--model gemma4:latest`)
- **Root fix needed:** When MODEL="auto", call `discover_backend().list_models()` and pick the first available model

### B3: Adapter not rebuilt after MODEL changes in `__main__`
- **Severity:** High (makes B2's workaround ineffective until this is also fixed)
- **Symptom:** Even with `--model gemma4:latest`, health shows `model_family: "default"` and LLM returns `(no response)`
- **Cause:** `adapter = ModelAdapter(MODEL)` runs at module level with MODEL="auto". `__main__` reassigns MODEL but never rebuilds adapter, so LLM calls still use the stale adapter with model="auto".
- **Fix:** Added adapter rebuild after MODEL re-resolution:  
  `if MODEL != "auto" or adapter.family == "default": adapter = ModelAdapter(MODEL)`

### B4: Missing `gemma4` in `use_raw_generate` whitelist
- **Severity:** Low (Gemma 4 uses chat API correctly via the `else` branch)
- **Status:** Not a bug for now — `_raw=False` → `/api/chat` which is correct for Gemma 4. Only matters if Gemma 4 ever needs raw generate.
