# Miser v1.2 — Code Review

**Reviewer:** @guyu-adam
**Date:** 2026-05-21
**Repository:** guyu-adam/miser

---

## Overall Assessment

v1.1 → v1.2 响应了 CODE_REVIEW 的 9 条建议，6 条已修复、2 条未修、1 条部分完成。测试目录从无到有、多语言 outline、pip install、分块蒸馏都是实打实的改进。但 Windows 支持和 token 精确计数仍然缺失，README 中的 benchmark 数字未标注估算性质，存在误导风险。

| Dimension | v1.2 Rating | v1.1 Rating | v1.0 Rating | Change |
|-----------|------------|-------------|-------------|--------|
| Concept/Value | ★★★★★ | ★★★★★ | ★★★★★ | — |
| Security | ★★★★☆ | ★★★★☆ | ★★☆☆☆ | — |
| Maintainability | ★★★★☆ | ★★★★☆ | ★★★☆☆ | — |
| Engineering Completeness | ★★★★☆ | ★★★☆☆ | ★★★★☆ | tests/ + pyproject.toml + logging |
| Cross-platform | ★★☆☆☆ | ★★☆☆☆ | ★★☆☆☆ | 仍无 Windows 支持 |
| Honesty/Accuracy | ★★★☆☆ | ★★★☆☆ | — | benchmark 仍无"估算"标注 |

---

## v1.0 问题修复状态

| # | Issue | Status |
|---|-------|--------|
| 1 | `eval()` arbitrary code execution | ✅ `_safe_eval()` AST-based evaluator |
| 2 | `shell=True` dangerous commands | ✅ Pattern-based blocking in `run_shell()` |
| 3 | Thread-unsafe `_tokens_saved` | ✅ `threading.Lock` added |
| 4 | Zero authentication | ✅ `MISER_AUTH_TOKEN` option |
| 5 | Fragile path parsing | ✅ Quote-aware parsing |
| 6 | Context mismatch 0.05 → 0.15 | ✅ Threshold relaxed |
| 7 | Memory size unbounded | ✅ `MAX_NOTES=200` with eviction |
| 8 | Batch LLM no backpressure | ✅ Capped at 3 with error response |
| 9 | Regex routing fragile | ✅ `EXPLICIT_ROUTES` dict, regex only for `/ask` fallback |
| 10 | Mixed Chinese/English patterns | ✅ `I18N_PATTERNS` config dict |
| 11 | `miser.py` 726 lines single file | ✅ Split into `miser.py` + `tools.py` + `memory.py` |
| 12 | Flask `threaded=True` deprecated | ✅ Removed |

---

## v1.1 → v1.2 问题修复核查

### 13. 没有 `tests/` 目录 → ✅ 已修复

`tests/` 目录已添加，包含 3 个模块 43 条 pytest case：

```
tests/
├── __init__.py
├── test_tools.py      # safe_eval, file ops, grep, token counter, shell safety (22 tests)
├── test_quality.py    # classification, offload routing, confidence scoring (15 tests)
└── test_adaptive.py   # adaptive router, cooldown, independence, escalation (6 tests)
```

`pyproject.toml` 已配置 `[tool.pytest.ini_options]`，`pip install -e .[dev]` 后可直接 `pytest`。

**遗留问题:** 仍然没有 GitHub Actions CI 配置，测试只能在本地手动运行。TEST_REPORT.md 仍然无法通过 CI 自动复现。

### 14. `outline_file` 只支持 Python → ✅ 已修复

`tools.py:148-160` 新增 `_OUTLINE_PATTERNS` dict，按扩展名分派解析器：

| 语言 | 后缀 | 匹配模式 |
|------|------|---------|
| Python | `.py` | `def / class / async def` |
| JavaScript | `.js` | `function / class / const / let / var / export` |
| TypeScript | `.ts` | `function / class / const / interface / type / enum / export` |
| TSX | `.tsx` | `function / class / const / interface / type / export` |
| Go | `.go` | `func / type / var / const` |
| Rust | `.rs` | `fn / pub fn / struct / enum / trait / impl / mod / const / type` |
| Java | `.java` | `public/private/protected class / interface / enum` |
| Ruby | `.rb` | `def / class / module / attr_` |
| Shell | `.sh` | `function name / name()` |
| SQL | `.sql` | `CREATE TABLE/INDEX/VIEW/FUNCTION/PROCEDURE/TRIGGER` |

未匹配的后缀 fallback 到 Python 模式。设计合理，覆盖了主流后端语言。前端框架的 `.vue` / `.svelte` 暂未覆盖，但影响面不大。

### 15. 零 Windows 支持 → ❌ 未修复

- 没有 `install.ps1`
- 没有 Windows Service wrapper
- `install.sh:88` 仍然写 "⚠ Windows: auto-start not yet supported"
- `TEST_REPORT.md:163` 确认 Windows 需手动启动
- README 没有提 Windows 手动启动步骤

这是本次最明显的未交付项。建议中的最低要求（README 写明 Windows 手动步骤）也未实现。

**建议:** 至少补充 README 中的 Windows 手动启动说明（`python miser.py` + 依赖安装），让 Windows 用户不至于完全无法上手。

### 16. 没有配置系统 → ⚠️ 部分修复

`miser.py:36` 端口已改为 `MISER_PORT` 环境变量，不再硬编码 7860。但：
- 没有 `.env` 文件自动加载
- 没有 `config.yaml` / `config.toml` 文件支持
- 没有 CLI 参数（`--port`, `--model` 等）

当前只有 3 个环境变量 (`MISER_MODEL`, `MISER_AUTH_TOKEN`, `MISER_PORT`)，对于个人工具来说够用，不需要过度工程化。

### 17. 不能 `pip install` → ✅ 已修复

`pyproject.toml` 已添加：
- `[build-system]` 配置 setuptools
- `[project]` 元数据、依赖 (`flask`, `requests`, `rich`)
- `[project.optional-dependencies]` dev (`pytest`, `pytest-cov`) 和 tiktoken
- `[project.scripts]` 入口点 `miser = client:main`
- `[tool.pytest.ini_options]` 测试配置

支持 `pip install -e .` 可编辑安装，`pip install -e .[dev]` 含测试依赖。

### 18. 日志系统缺失 → ✅ 已修复

`miser.py:572-585` 新增 structured logging：
```python
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler("miser.log"),
        logging.StreamHandler(),
    ]
)
```

同时将 werkzeug 日志级别提升为 WARNING 避免噪音。启动时记录版本号和端口。

**小问题:** `import logging` 写了两次（line 572 和 line 576），无伤大雅但可以合并。

### 19. `prefetch.py` 命中率统计是假的 → ✅ 已修复

`prefetch.py:64-81` — `prefetch()` 现在记录每次预取的 `(filepath, timestamp)`。

`prefetch.py:99-115` — `check_hit()` 改为对比文件 `st_atime` 与预取时间戳，0.5 秒窗口内判定为命中。不再是"访问过就算 hit"。

实现合理。`st_atime` 方案是 OS 无关的（Windows/Linux/macOS 均可用），比建议中的 `os.mincore()`（仅 Linux）更具可移植性。

### 20. `condenser.py` 硬截断 + 无重试 → ✅ 已修复

`condenser.py:86-98` — 长文本分块策略：每块 6000 字符，块间重叠 500 字符，每块独立蒸馏后合并。

`condenser.py:117-134` — `_call_ollama()` 支持 retry（默认 1 次重试），失败返回空字符串。

`distill()` 中所有 chunk 都失败时返回原文（安全降级）。

### 21. Token 计数是估算值 → ❌ 未修复

核心问题依旧——所有 token 计数基于 `chars / 4` 估算：

```python
# tools.py:32-33
_tokens_saved += int(chars / 4)
```

`pyproject.toml` 虽然添加了 `tiktoken` 作为 optional dependency，但代码中未集成：
```python
# 没有任何 `import tiktoken` 或 `tiktoken.get_encoding()`
```

README 仍然写 "18,880 tokens saved (98.7% reduction)" 不带 `~` 或 "(estimated)" 标注。`/status` 端点的字段名改成了 `tokens_saved_est`（miser.py:188），这是好的，但 README 和面向用户的数字没有同步标注。

**这是诚信问题，不是工程问题。** 用户看到 "18,880 tokens" 会认为是精确值，实际偏差在 ±15-20%。

**建议:** 在 README 所有 token 数字前加 `~`，或在脚注中说明是估算值。

---

## 代码审查中新发现的问题

### 22. `miser.py` 重复 import logging

```python
# miser.py:572
import logging
# miser.py:576
import logging as _log
```

两次 import 同一个模块，第二个别名覆盖了第一个。第一个 import 完全没用。

**建议:** 删掉 line 572 的 `import logging`。

### 23. 测试文件依赖 `sys.path.insert` hack

```python
# tests/test_tools.py:5
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
```

三个测试文件都用了这个。有了 `pyproject.toml` + `pip install -e .` 之后，测试应该能直接 `import tools`，不再需要 `sys.path` hack。

**建议:** 在 `pip install -e .` 之后删掉测试中的 `sys.path.insert`，或者至少在 `conftest.py` 中统一处理。

### 24. `condenser.py` chunk 合并丢失信息

```python
# condenser.py:114
return "\n".join(f"[Part {i+1}] {d}" for i, d in enumerate(digests))
```

多个 chunk 各自蒸馏后只是简单拼接，没有对合并后的 digest 做去重或一致性检查。两个 chunk 可能输出重复的函数签名、交叉引用被切断。

**建议:** 多 chunk 合并后做一次去重（至少对函数名/签名级别的去重）。

### 25. 没有 `conftest.py` 或 shared fixtures

三个测试文件各自重复 `sys.path.insert` 和 import 逻辑。没有共享的 fixtures、没有 mock 工具的统一配置。

**建议:** 添加 `tests/conftest.py` 统一 path setup 和共享 fixtures。

---

## 架构层面的观察

### 模块依赖链更新

v1.2 的核心依赖图：

```
miser.py (Flask routes, 622 lines)
├── tools.py       (Zero-LLM ops — shell, file, grep, outline, patch)
├── model_adapter.py (17 model families, prompt format + response clean)
├── memory.py      (key-value store, 200 notes max, auto-evict)
├── quality.py     (static CRITICAL/STANDARD/SAFE classifier)
├── adaptive.py    (self-learning per-category success rate tracker)
├── condenser.py   (semantic distillation via local LLM, chunking + retry)
├── prefetch.py    (Markov-chain file access predictor with timestamp-based hit detection)
└── client.py      (Python SDK wrapper, quality gate integration)
```

`miser.py` 仍然是 God module（622 行），所有 Flask 路由都在这里。但相对于 v1.0 的 726 行单文件、v1.1 的多模块拆分，v1.2 至少在路由端的代码质量有提升。

### `quality.py` / `adaptive.py` 的分工重叠（未修复）

CODE_REVIEW v1.1 提出的"两个模块都做 offload 判断，没有统一 pipeline"的问题仍然存在：
- `quality.py` — 静态关键词白名单，判断 CRITICAL/STANDARD/SAFE
- `adaptive.py` — 动态成功率学习，判断是否冷却

`client.py` 中两者分别调用，没有合并为单一 `Router` 类。不过当前代码量不大，暂时不需要强制合并。

---

## What's Well Done

- **`_OUTLINE_PATTERNS` 设计** — 10 种语言覆盖到位，fallback 到 Python 的兜底策略合理
- **`prefetch.py` 的 `st_atime` 方案** — 比建议中的 `os.mincore()`（仅 Linux）更具跨平台性
- **`condenser.py` 分块策略** — 6000 字符 + 500 重叠是合理的工程权衡，比原来的硬截断 8000 好得多
- **`pyproject.toml` 配置规范** — 完整的 setuptools 配置 + extras + scripts，质量不错
- **测试覆盖三个维度** — tools (确定性操作)、quality (路由决策)、adaptive (学习行为)，覆盖了核心风险点

---

## Summary

v1.1 的 9 条建议中 6 条已修、2 条未修（#15 Windows 支持、#21 token 估算标注）、1 条部分完成（#13 缺 CI）。工程质量在持续提升。

**当前最需要修的三个问题：**

1. **Token 估算标注** — README benchmark 数字加 `~` 或 "estimated"（一行改动，但影响诚信）
2. **Windows 上手说明** — 至少 README 写清楚 Windows 怎么跑起来（不改代码，只改文档）
3. **重复 import** — `miser.py` line 572 的无效 `import logging`（一行删除）

这三个加起来不到 10 行改动，修完后 v1.2 就是一个信得过的版本。
