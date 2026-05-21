# Miser v1.0 — Code Review

**Reviewer:** @guyu-adam  
**Date:** 2026-05-21  
**Repository:** guyu-adam/miser

---

## Overall Assessment

This is a valuable project — the concept is clear and it solves a real problem (saving API tokens = saving money). The code structure is decent overall, but there are several **security issues** and **engineering details** that need attention.

| Dimension | Rating | Notes |
|-----------|--------|-------|
| Concept/Value | ★★★★★ | Solves a real pain point |
| Security | ★★☆☆☆ | `eval()` + `shell=True` need fixing |
| Maintainability | ★★★☆☆ | Single file too long, fragile regex routing |
| Engineering Completeness | ★★★★☆ | Test reports, docs, install scripts all included |

---

## Critical Issues

### 1. `eval()` arbitrary code execution — `miser.py:311`

```python
(re.compile(r"^[\d\s\+\-\*\/\.\^\(\)]+$"),
 lambda t: str(eval(t.replace("^", "**"))))
```

Even though the regex restricts the character set, an attacker can still craft payloads to escape the sandbox. For example, chain-based attacks like `(1).__class__.__bases__[0].__subclasses__()` can break out. **Recommendation:** Use `ast.literal_eval()` or a dedicated math evaluator like `numexpr.evaluate()`.

### 2. `shell=True` in `_shell()` — `miser.py:163`

All `/run` endpoint commands execute via `shell=True`. While this is a local-only service, if port 7860 is ever exposed through port forwarding or reverse proxy, arbitrary system commands could be executed. **Recommendation:** Add dangerous character validation at minimum; ideally split the shell and file-operation endpoints into separate permission levels.

### 3. Thread-unsafe global `_tokens_saved` — `miser.py:34-37`

```python
_tokens_saved = 0
def _count_saved(chars: int):
    global _tokens_saved
    _tokens_saved += int(chars / 4)
```

`+=` is not atomic in Python — concurrent threads will have race conditions causing lost counts. **Recommendation:** Use `threading.Lock`.

---

## Medium Issues

### 4. Zero authentication on HTTP endpoints

All endpoints on port 7860 have no authentication. This is fine in a purely local environment, but if anyone configures a reverse proxy or port forwarding to the public internet, it becomes a security risk. **Recommendation:** Add a simple token check, at least as an option.

### 5. Fragile path parsing in `_extract_path` — `miser.py:316-321`

The regex `(~/[^\s,;'"\)]+` cannot handle file paths with spaces. **Recommendation:** Use `shlex.split()` or accept JSON-formatted paths from the API.

### 6. Context mismatch threshold too aggressive — `client.py:79`

```python
if ctx_words and len(overlap) / len(ctx_words) < 0.05:
```

A threshold of 0.05 means that if 95% of context keywords don't appear in the output, it's flagged as `CONTEXT_MISMATCH`. This will generate many false positives. **Recommendation:** Raise to 0.15–0.20.

### 7. Memory files have no size protection — `miser.py:64-66`

`memory.json` and `embeddings.json` have no upper size limit. After long-running use, they will continuously grow. Although only the last 40 entries are kept in `history` and `embeddings`, the `notes` dictionary grows without bound. **Recommendation:** Cap the `notes` dictionary size as well, or add a TTL mechanism.

### 8. `batch()` allows LLM tasks without concurrency control — `miser.py:643-673`

The `ask` type in batch directly calls `run_task`, which triggers LLM inference. If a batch includes multiple LLM tasks, Ollama gets flooded. **Recommendation:** Either disallow LLM operations in batch, or cap the count and add backpressure.

---

## Code Style / Maintainability

### 9. `DIRECT_ROUTES` regex routing is fragile — `miser.py:303-314`

Intent routing via regex is a creative idea, but it becomes a regex maintenance nightmare as rules grow. **Recommendation:** Switch to explicit endpoint calls; keep the regex routing as a fallback only for the `/ask` general-purpose endpoint.

### 10. Mixed Chinese/English regex patterns — `miser.py:304,312`

```python
r"(ls|list|列出?|有什么|有哪些).{0,20}?(文件|folder|目录|dir|~/|/\w)"
```

Hardcoding Chinese match words makes internationalization difficult. **Recommendation:** Extract these into a config dictionary.

### 11. `miser.py` is too long at 726 lines in a single file

**Recommendation:** Split into:
- `server.py` — Flask routes
- `tools.py` — Zero-LLM utility functions
- `memory.py` — Memory class

### 12. Flask `threaded=True` is deprecated — `miser.py:696`

In Flask 2.3+, the `threaded` parameter is deprecated; it's threaded by default. **Recommendation:** Remove the parameter and consider using `waitress` or `gunicorn` for production.

---

## What's Well Done

- **`model_adapter.py`** — The multi-model adaptation layer is well-designed. Family detection → prompt builder → response cleaner, three-layer separation is clean and extensible.
- **`client.py` supervision layer** (`_check_llm`) — A good defensive design that catches hallucinations and syntax errors.
- **Zero-LLM / Local-LLM two-tier split** — Clear conceptual separation with measured token savings backed by real data.
- **`/batch` endpoint** — Reduces HTTP round-trips, well-designed.
- **`TEST_REPORT.md`** — Complete test report with 62 test cases, rigorous and thorough.

---

## Summary

**Priority fix: the `eval()` and `shell=True` security issues.** After that, splitting `miser.py` would improve maintainability, and the project is ready to ship.
