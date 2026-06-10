# Miser Bug Tracker

## B1: adapter not rebuilt after CLI MODEL override

**Found:** 2026-06-10, macOS / Windows  
**Severity:** Critical — all `/v1/ask` calls return `(no response)` when `--model` differs from config

**Root cause:** Module-level `adapter = ModelAdapter(MODEL)` runs before `__main__`, using config MODEL (often "auto"). When `__main__` reassigns `MODEL = cli_cfg["model"]`, the adapter is NOT recreated — it still holds the old model/family.

**Fix:** `miser.py` line 672: add `adapter = ModelAdapter(MODEL)` after MODEL reassignment.

**Commit:** `fix: rebuild adapter when CLI MODEL differs from config`

---

## B2: thinking models consume all tokens with think_budget

**Found:** 2026-06-10, macOS (qwen3.5:4b)  
**Severity:** High — `/v1/ask` returns `(no response)` for thinking-family models

**Root cause:** `generate_payload` allocated `think_budget = 2400` for thinking models (qwen3, deepseek-r1, deepseek-r2). These models already output native thinking in their generation; the extra budget means all allocated tokens are consumed by thinking steps, leaving no room for the actual answer. Compounded by the fact that qwen3.5:4b's chat API returns empty `content` and puts everything in `thinking` field.

**Fix:** `model_adapter.py` line 301: set `think_budget = 0` unconditionally. The model's native thinking is already baked in; we just need the final answer tokens.

**Commit:** `fix: remove think_budget — thinking models consume all tokens before answer`

---

## B3: gemma4 not routed to raw generate API

**Found:** 2026-06-10, Windows (gemma4:latest, 8B)  
**Severity:** High — `/v1/ask` returns 500 or incomplete thinking output

**Root cause:** gemma4 returns family `"gemma4"` (separate from `"gemma"`). `use_raw_generate()` did not include `"gemma4"`, so it fell through to chat API. Like qwen3.5, gemma4's chat API returns empty `content` with all output in `thinking` field. Additionally, `build_prompt` only matched `family == "gemma"`, not `"gemma4"`.

**Fix:** 
1. `use_raw_generate`: add `"gemma4"` to the family list → forces generate API with `raw: true`
2. `build_prompt`: change `if family == "gemma":` → `if family in ("gemma", "gemma4"):`

**Commit:** `fix: route gemma4 through raw generate API (same as gemma)`

---

## Resolution summary (2026-06-10)

| Bug | Platform | Model | Symptom | Root Fix |
|---|---|---|---|---|
| B1 | Mac + Win | all | `(no response)` | Rebuild adapter after MODEL change |
| B2 | Mac | qwen3.5:4b | `(no response)` | Kill think_budget |
| B3 | Win | gemma4:latest | 500 / thinking output | gemma4 → raw generate |
