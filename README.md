# Miser — Save 98% API Tokens with Your Local GPU

**Stop burning cloud tokens on file reads. Offload everything to your local Ollama GPU.**

Miser runs at `localhost:7860` and intercepts the expensive parts of AI coding sessions:
- **File ops, grep, tree** → served instantly from disk, zero LLM, zero tokens
- **Code gen, explain, fix, review, tests** → runs on your local Ollama model, zero API cost

Works with **Claude Code**, **Codex CLI**, **Aider**, or any agent that can call HTTP.

---

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://python.org)
[![Ollama](https://img.shields.io/badge/LLM-Ollama-green.svg)](https://ollama.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Zero API Cost](https://img.shields.io/badge/local%20LLM%20ops-$0.00-brightgreen.svg)](#)

---

## Live Demo (May 2026)

**[▶ Play terminal recording](demo.cast)** — `asciinema play demo.cast`

```
╭───────────────────────────────────────────────────────────────────╮
│ ⚡ Miser v1.1 — Save 98% API Tokens with Your Local GPU          │
│ Claude Code Co-Processor  |  ollama://qwen3.5:4b  |  $0 API Cost │
╰───────────────────────────────────────────────────────────────────╯

───────────────── SESSION SUMMARY ─────────────────
Operation                Without Miser    With Miser    Saved    Pct
─────────────────────────────────────────────────────────────────────
Read+Outline 300-lines             1,936          109    1,827    94%
Project mapping (6 files)         16,069          144   15,925    99%
Debug & Fix error                    228           $0      228   100%
Generate unit tests                  900           $0      900   100%
─────────────────────────────────────────────────────────────────────
TOTAL                             19,133          253   18,880    98%
─────────────────────────────────────────────────────────────────────

💰 Per session:  $0.0574 → $0.0008  (18,880 tokens saved)
   Per month:     $3.44   → $0.05    ($3.40 saved)
   Per year:      $41.33  → $0.55    ($40.78 saved)
```

*Benchmarked with Claude Sonnet pricing ($3/MTok) on qwen3.5:4b via Ollama, Linux.*

---

## The Problem

Every time your AI assistant reads a file to understand it, map its structure, or generate a test — it burns tokens:

| What your agent does | Tokens consumed | Cost |
|---|---|---|
| `Read` a 300-line file to find one function | ~1,900 tokens | $0.006 |
| `Read` 6 files to map a project | ~16,000 tokens | $0.048 |
| Generate a test suite for a module | ~900 tokens | $0.003 |
| Debug + fix one error | ~230 tokens | $0.001 |

In a typical 2-hour Claude Code session, **40-60% of token spend is on these mechanical tasks**. That's **~$0.06 you're burning per session** just for file understanding.

## The Solution

Miser intercepts those calls and handles them locally:

| Expensive cloud call | Miser equivalent | Token cost |
|---|---|---|
| `Read(large_file)` → ~1,936 tokens | `W.outline(path)` | **~109 tokens** (94% saved) |
| Read 6 files → ~16,069 tokens | `W.tree(project)` | **~144 tokens** (99% saved) |
| Generate tests yourself | `W.test(path)` | **$0.00** (local GPU) |
| Analyze error + write fix | `W.fix(error, code=...)` | **$0.00** (local GPU) |
| Read to understand module | `W.explain(path)` | **$0.00** (local GPU) |
| Code review | `W.review(path)` | **$0.00** (local GPU) |

**Real measurement (May 2026): saves 18,880 tokens per session — 98% reduction.**

---

## Quick Start

```bash
git clone https://github.com/guyu-adam/miser.git
cd miser
bash install.sh          # installs deps, pulls qwen3.5:4b, starts service
```

Then in your Claude Code session (or any agent):

```python
import sys; sys.path.insert(0, '/path/to/miser')
from client import W

W.outline("~/project/app.py")          # function/class map — ~109 tokens (was 1,936)
W.grep("~/project/app.py", "def auth") # find a function — ~50 tokens
W.explain("~/project/utils.py")        # understand module — $0 (local GPU)
W.fix("TypeError: NoneType", code="…") # debug + fix — $0 (local GPU)
W.test("~/project/utils.py")           # write tests — $0 (local GPU)
```

**Requirements**: Python 3.10+, [Ollama](https://ollama.com) installed and running.
GPU optional — works on CPU, just slower (4b model: ~40s on CPU, ~10s on GPU).

---

## Full API

### Zero-LLM ops — instant, no model needed

```python
W.outline(path)               # → "def foo [L12]\nclass Bar [L34]\n..."
W.grep(path, pattern, ctx=2)  # → matching lines with context
W.tree(path, depth=2)         # → directory tree string
W.exists(path)                # → {"exists": True, "size_kb": 12}
W.run("git diff --stat")      # → shell output
W.read(path)                  # → file content (use sparingly)
W.write(path, content)        # → write file
W.patch(path, old, new)       # → find-and-replace in file
```

### Local-LLM ops — runs on Ollama, zero API tokens

```python
W.explain(path_or_code)              # plain-English explanation
W.fix(error_msg, code="...")         # error message → suggested fix
W.test(path, function="parse")       # generate pytest tests
W.review(path)                       # bug + improvement review
W.codegen("write RSI indicator")     # code generation
W.summarize(path, focus="errors")    # compress file to bullets
W.git_summary(path, n=10)            # recent commits summary
W.ask("any freeform task")           # general purpose
```

### Batch — one HTTP round-trip for multiple ops

```python
results = W.batch([
    ("outline", "~/project/app.py"),
    ("outline", "~/project/models.py"),
    ("run",     "git status"),
    ("exists",  "~/project/.env"),
])
```

---

## Integration with Claude Code

Add to your `CLAUDE.md`:

```markdown
## Miser — Local Token Saver (ALWAYS USE THIS)

Miser runs at http://localhost:7860.

import sys; sys.path.insert(0, '/path/to/miser')
from client import W

| Task | Do NOT do this | Do THIS instead |
|------|---------------|-----------------|
| Map file structure | Read(large_file) | W.outline(path) |
| Find one function | Read(large_file) | W.grep(path, "def fn") |
| Understand a module | Read + reason | W.explain(path) |
| Write tests | Generate yourself | W.test(path) |
| Debug error | Reason yourself | W.fix(error, code=ctx) |
| Multiple lookups | Sequential Reads | W.batch([...]) |
```

---

## Live Benchmarks (May 2026)

Tested on miser's own codebase (6 Python files, 64K chars), with `qwen3.5:4b` on Ollama, Linux:

```
─── Zero-LLM endpoints ───
  ✓ status             1ms
  ✓ exists             1ms
  ✓ read               1ms
  ✓ outline            5ms
  ✓ grep               4ms
  ✓ tree               2ms
  ✓ run                4ms
  ✓ batch (2x)         2ms

─── Local-LLM endpoints ───
  ✓ codegen           1.0s
  ✓ fix               0.9s
  ✓ explain           0.6s
  ✓ review            0.4s
  ✓ test             10.1s
  ✓ summarize         1.0s
  ✓ ask               0.2s
```

### Per-session savings (measured)

| Metric | Without Miser | With Miser | Savings |
|---|---|---|---|
| File reads & mapping | 18,005 tokens | 253 tokens | **-98.6%** |
| LLM ops (tests, explain, fix, review) | 1,128 tokens | $0.00 | **-100%** |
| **Total session tokens** | **19,133** | **253** | **-98.7%** |
| **Estimated cost (Claude Sonnet)** | **$0.057** | **$0.001** | **-$0.057/session** |
| **Per month (60 sessions)** | **$3.44** | **$0.05** | **-$3.40** |
| **Per year (720 sessions)** | **$41.33** | **$0.55** | **-$40.78** |

---

## Changing the Model

```bash
ollama pull mistral:7b
MISER_MODEL=mistral:7b bash start.sh
```

Tested models: `qwen3.5:4b` (default, fast), `qwen3.5:latest` (8B, smarter),
`mistral:7b`, `llama3.1:8b`, `phi4`, `gemma3:4b`, `deepseek-coder:6.7b`.

---

## Architecture

```
Claude Code / Aider / Codex
        │  HTTP POST localhost:7860
        ▼
  ┌─────────────────────┐
  │      miser.py       │
  │  ┌───────────────┐  │
  │  │ tools.py      │──┼──► disk / shell  (<50ms)
  │  │ Zero-LLM ops  │  │
  │  └───────────────┘  │
  │  ┌───────────────┐  │
  │  │ memory.py     │──┼──► Ollama API   ($0)
  │  │ Local-LLM ops │  │
  │  └───────────────┘  │
  └─────────────────────┘
```

---

## License

MIT
