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

---

# 商业化评估 v2（基于 v1.3）

**评估日期:** 2026-05-21
**评估对象:** Miser v1.3（阶段 1 商业化 P0 交付后）
**上一轮:** v1.2 评估结论为"开源可用、商业不足"，阶段 1 的 5 个 P0 项已全部交付。

---

## 一、v1.2 → v1.3 进展

v1.3 提交对标了上轮评估阶段 1 的 P0 项，交付质量超出预期：

| 事项 | 状态 | v1.3 实现 |
|------|------|----------|
| health check | ✅ | `/health` 返回 version/worker/queue/model |
| 请求队列 | ✅ | `queue.py` — FIFO bound queue (max=10, timeout=60s)，自动排空 |
| CI/CD | ✅ | GitHub Actions, Python 3.10-3.13 矩阵, pytest + coverage |
| install.sh 版本号 | ✅ | v1.0 → v1.3 |
| CHANGELOG | ✅ | 完整 4 版本记录 |
| 覆盖率 | ⚠️ | CI 有 `--cov` 但未接入 codecov/codacy |

**v1.3 新增代码质量评估：**

| 做得好 | 需要改进 |
|--------|---------|
| `queue.py` 自排空设计优雅——`run_task()` finally 块自动取下一任务 | `task_id=str(id(d))` 用 Python 对象 id，GC 后可能重复 |
| `/ask` 返回 202 + position，用户体验好 | `queue.py:57` `\|` 类型注解仅 Python 3.10+ 可用 |
| Zero-LLM 端点不受队列影响（仍直接执行） | `/chat`、`/codegen` 仍返回 429（未接入队列） |
| 日志格式保持文本但输出稳定 | 结构化日志（JSON）仍未实现 |

---

## 二、当前状态：v1.3 评分矩阵

| 维度 | v1.2 | v1.3 | 变化 |
|------|------|------|------|
| 产品/价值主张 | ★★★★☆ | ★★★★☆ | — |
| 安全 | ★★★☆☆ | ★★★☆☆ | — |
| 可靠性/容错 | ★★★☆☆ | ★★★★☆ | ↑ 队列替代 429，health check |
| 性能 | ★★★★☆ | ★★★★☆ | — |
| 分发/部署 | ★★★☆☆ | ★★★☆☆ | — |
| 测试 | ★★★★☆ | ★★★★☆ | ↑ CI 矩阵 4 版本 |
| 监控/可观测 | ★★★☆☆ | ★★★★☆ | ↑ health check + queue stats |
| API 设计 | ★★★☆☆ | ★★★☆☆ | — |
| 文档 | ★★★★☆ | ★★★★★ | ↑ CHANGELOG |
| 代码质量 | ★★★★☆ | ★★★★☆ | — |
| 法务/合规 | ★★★☆☆ | ★★★☆☆ | — |
| 竞争格局 | ★★★★☆ | ★★★★☆ | — |
| **综合** | **★★★☆☆** | **★★★★☆** | **↑ 进入"可信赖开源项目"** |

---

## 三、v1.3 审查新发现的问题

### 26. `task_id=str(id(d))` — 任务 ID 不唯一

```python
# miser.py:235
task_id=str(id(d)),
```

`id(d)` 返回 Python 内存地址，对象被 GC 后可被新对象复用。多个请求先后到来时可能产生重复 ID。

**建议:** 改为 `str(uuid.uuid4())[:8]`。

### 27. `queue.py` 类型注解不兼容 Python 3.9

```python
# queue.py:49
def dequeue(self) -> QueuedTask | None:
```

`X | None` 语法需要 Python 3.10+。`pyproject.toml` 声明 `requires-python = ">=3.10"`，所以实际上没问题，但 CI 的 3.10-3.13 矩阵中 3.10 是这个语法的最后一个兼容版本。

### 28. `/chat` 和 `/codegen` 未接入队列

```python
# miser.py:254 — 仍然是旧逻辑
if st.status == "WORKING": return jsonify({"error":"busy"}), 429

# miser.py:400 — 仍然是旧逻辑
if st.status == "WORKING": return jsonify({"error":"busy"}), 429
```

`/ask` 已经优雅排队，但 `/chat` 和 `/codegen` 仍然是硬拒绝。这三个端点行为不一致。

**建议:** 统一接入队列，或者至少在文档中说明差异。

### 29. 日志不是 JSON 结构化

当前日志格式：
```
%(asctime)s [%(levelname)s] %(message)s
```

生产环境下无法被 ELK/Loki/Datadog 解析。上一次评估标记为 P0 但 v1.3 未实现。

**建议:** 增加 `--log-format json|text` 选项，JSON 格式输出 `{"timestamp": "...", "level": "...", "message": "...", "module": "..."}`。

### 30. 无优雅关闭

Flask 开发服务器没有 SIGTERM/SIGINT 处理器。进程被 kill 时排队的任务直接丢失。

**建议:** 注册 `signal.signal(signal.SIGTERM, handler)` 在关闭前排空队列。

---

## 四、v1.3.1 验收总结

v1.3.1 交付后，上轮第一期（工程健壮性）8 项中 7 项完成：

| # | 事项 | 状态 |
|---|------|------|
| 1 | 修复 task_id | ✅ `uuid4()[:8]` |
| 2 | 结构化日志 | ✅ `MISER_LOG_FORMAT=json` + `JsonFormatter` |
| 3 | 优雅关闭 | ✅ SIGTERM/SIGINT → 排空队列 → 退出 |
| 4 | 统一队列接入 | ✅ `/ask` `/chat` `/codegen` 全部返回 202 |
| 5 | Docker | ✅ Dockerfile + docker-compose（Ollama sidecar + healthcheck） |
| 6 | 集成测试 | ✅ 14 个 Flask test client 用例（8 端点 + health/batch/memory） |
| 7 | 覆盖率 badge | ❌ 唯一未完成项 |
| 8 | 输入大小限制 | ✅ `MAX_CONTENT_LENGTH=5MB` |

**当前测试规模:** 57 条（43 unit + 14 integration），测试文件 5 个，CI 矩阵 Python 3.10-3.13。

---

## 五、下一阶段：商业化 + 封装（合并路线图）

v1.3.1 工程基底已经牢固。下阶段同时推进两条线——**安全与 API 治理**（让产品可信赖）+ **封装与分发**（让用户能下载就用）。两线并行，按依赖关系分为三期。

### 第一期：安全底线 + CLI 封装（3-4 天）— 达到"可公开分发"

两线并行：安全侧补齐生产级底线，封装侧做出第一个可双击运行的安装包。

| # | 线 | 事项 | 优先级 | 工作量 | 说明 |
|---|----|------|--------|--------|------|
| 1 | 安全 | rate limiting | P0 | 2h | Flask-Limiter，`/ask` 30/min、Zero-LLM 200/min |
| 2 | 安全 | API key hashing | P0 | 1h | `MISER_AUTH_TOKEN` 改为 SHA256 hash 存储和比对 |
| 3 | 安全 | CORS 白名单 | P0 | 0.5h | `flask-cors`，仅允许 `localhost` / `127.0.0.1` |
| 4 | 安全 | 安全扫描 CI | P0 | 1h | bandit + safety 加入 GitHub Actions |
| 5 | 安全 | error code 标准化 | P1 | 1h | 统一 `{"error": {"code": "E_xxx", "message": "..."}}` |
| 6 | 封装 | PyInstaller 打包 | P0 | 2h | `miser.spec`，打出单文件 exe/app |
| 7 | 封装 | 首次运行向导 | P0 | 2h | 检测 Ollama → 引导安装 → 自动 pull 模型 → 启动服务 |
| 8 | 封装 | CLI 参数 | P0 | 1h | `--port` / `--model` / `--log-format` / `--auth-token` 替代纯环境变量 |
| 9 | 封装 | 版本自检 | P1 | 0.5h | `miser --version` + 启动时检查 PyPI 最新版本 |

**第一期交付物:**
- 安全：rate limit 启用、auth token 哈希化、CORS 锁定、安全扫描跑在 CI 上
- 封装：`miser.exe` (20MB) / `Miser.app` (25MB) 可双击启动，首次运行自动引导

### 第二期：API 治理 + Tauri 托盘 App（4-6 天）— 达到"可商业分发"

安全侧进行 API 规范化和版本控制，封装侧从 CLI 升级到带托盘的桌面 App。

| # | 线 | 事项 | 优先级 | 工作量 | 说明 |
|---|----|------|--------|--------|------|
| 10 | API | API 版本化 | P0 | 2h | `/v1/read` `/v1/ask` 等，旧路由标记 deprecated 保留 |
| 11 | API | OpenAPI 文档 | P0 | 3h | `/v1/openapi.json` + Swagger UI 页面 |
| 12 | API | config.py 集中配置 | P0 | 2h | 环境变量 + CLI 参数 + 默认值统一加载和校验 |
| 13 | API | 响应格式标准化 | P1 | 1h | 所有端点统一 `{"data": ..., "meta": {"tokens_saved_est": N}}` |
| 14 | API | 覆盖率 badge | P1 | 0.5h | CI 接入 codecov.io |
| 15 | 封装 | Tauri 托盘壳 | P0 | 4h | 系统托盘 + 状态指示（绿/黄/红）+ 菜单 |
| 16 | 封装 | macOS 签名 + 公证 | P1 | 2h | Apple Developer 签名，消除 Gatekeeper 警告 |
| 17 | 封装 | Windows 签名 | P1 | 1h | 代码签名证书，消除 SmartScreen 警告 |
| 18 | 封装 | 自动更新 | P1 | 2h | 检测 GitHub Release 新版本 → 一键升级 |

**第二期交付物:**
- API：版本化端点 + OpenAPI spec + 统一响应格式，第三方可放心依赖
- 封装：Tauri 托盘 App，大小 ~30MB，macOS/Windows/Linux 三平台，支持签名分发

### 第三期：架构演进 + VS Code 插件（1-2 周）— 达到"平台级产品"

架构侧完成拆分和多 worker 以支持未来扩展，封装侧覆盖 VS Code 生态触达最大用户群。

| # | 线 | 事项 | 优先级 | 工作量 | 说明 |
|---|----|------|--------|--------|------|
| 19 | 架构 | 拆分 miser.py 路由 | P0 | 4h | `routes/zero.py` `routes/llm.py` `routes/admin.py` |
| 20 | 架构 | 多 worker 进程 | P0 | 2h | gunicorn/uvicorn + 共享队列（SQLite），突破单并发瓶颈 |
| 21 | 架构 | 断路器（Ollama） | P0 | 2h | 连续失败 5 次 → 熔断 60s → 半开探测 → 自动恢复 |
| 22 | 架构 | 响应缓存 | P1 | 2h | same path+params → 缓存结果（TTL 30s），Zero-LLM 命中率最高 |
| 23 | 架构 | Prometheus metrics | P2 | 2h | `/metrics`：`miser_tokens_saved` `miser_request_duration_ms` `miser_queue_depth` |
| 24 | 架构 | pre-commit hooks | P2 | 0.5h | ruff format + lint + bandit |
| 25 | 插件 | VS Code 插件 | P0 | 5h | `ext install miser`，侧边栏显示状态，一键启动/停止，用量统计 |
| 26 | 插件 | 插件配置页 | P1 | 2h | Ollama endpoint / model / port 设置，首次启动向导 |
| 27 | SDK | JS/TS SDK | P1 | 3h | `npm install miser-client`，对标 `client.py` 的 W API |

**第三期交付物:**
- 架构：路由拆分 + 多 worker + 断路器 + 缓存，可水平扩展
- 插件：VS Code 插件上线 Marketplace，安装量最大的分发渠道
- SDK：JS/TS 客户端，前端项目也能直接调 Miser

---

## 六、封装方案详解

### 三层封装策略

```
Layer 1: PyInstaller (v1.4)          ← 第一期
  └─ 单文件 .exe / .app
  └─ 内嵌 Python 3.12 + 所有依赖
  └─ 大小: ~20MB
  └─ 目标: 不需要装 Python 就能跑

Layer 2: Tauri Tray (v2.0)           ← 第二期
  └─ 系统托盘 + 菜单
  └─ 首次运行向导（检测 Ollama → 拉模型 → 启动）
  └─ 大小: ~30MB（Tauri ~3MB + PyInstaller ~25MB）
  └─ 目标: 普通开发者双击即用

Layer 3: VS Code Extension (v2.1)    ← 第三期
  └─ 侧边栏状态面板
  └─ 一键启动/停止
  └─ 用量统计（今日/本周/总计 token 节省）
  └─ 大小: ~2MB（纯 JS）
  └─ 目标: 覆盖所有 VS Code 用户
```

### 用户安装流程对比

```
现在:
  1. git clone https://github.com/guyu-adam/miser
  2. cd miser
  3. pip install flask requests rich
  4. 装 Ollama (去 ollama.com 下载)
  5. ollama pull qwen3.5:4b
  6. python miser.py
  7. 终端不能关
  → 门槛：需要 git、Python、pip、终端操作

v2.0 Tauri App:
  1. 下载 Miser.dmg (30MB)
  2. 双击安装，拖到 Applications
  3. 首次启动 → 弹出向导："需要 Ollama，点此安装" / "已安装 ✓"
  4. 自动 ollama pull → 进度条
  5. 完成 → 托盘图标变绿 → 可以使用了
  → 门槛：零。下载→双击→完事
```

---

## 七、不做的事（明确排除）

| 事项 | 排除原因 |
|------|---------|
| 多用户隔离 | 本地个人工具，SaaS 化之后再考虑 |
| billing / 付费系统 | 先积累用户，有需求再定价 |
| SSO / OAuth / LDAP | 本地 localhost 不需要企业认证 |
| SOC2 / GDPR 合规 | 无托管服务 = 不涉及用户数据处理 |
| 多区域部署 | 本地单机不存在多区域问题 |
| 白标 / OEM | 产品未验证，过早无意义 |
| K8s / Helm | 单机工具不需要容器编排 |
| GUI Dashboard | token 金额太小（$3/月），Web UI 的成本比省的钱还多 |

---

## 八、路线图时间线

```
Week 1 ──── 第一期（安全 + CLI 封装）
              rate limit · API key hash · CORS · 安全扫描 · PyInstaller · 首次运行向导 · CLI
              交付: v1.4 + miser.exe / Miser.app
                     "可公开分发的可信赖服务"

Week 2-3 ── 第二期（API 治理 + Tauri 托盘）
              API 版本化 · OpenAPI · config.py · 响应标准化 · Tauri 壳 · 代码签名 · 自动更新
              交付: v2.0 + Tauri 三平台安装包
                     "普通开发者下载即用的产品"

Week 3-4 ── 第三期（架构演进 + VS Code）
              路由拆分 · 多 worker · 断路器 · 缓存 · VS Code 插件 · JS SDK · Prometheus
              交付: v2.1 + VS Code 插件
                     "覆盖 VS Code 生态的平台级产品"

Beyond ──── 等待市场信号
              ├─ VS Code 插件安装量 > 1000 → 验证 PMF
              ├─ GitHub Stars > 500 → 启动社区运营
              ├─ 有用户问"怎么付费" → 设计定价模型
              └─ Anthropic 推出官方本地 offload → pivot 为质控中间件
```

---

## 九、更新后总评分（含封装维度）

| 维度 | v1.3.1 | 目标 v2.1 |
|------|--------|-----------|
| 产品/价值主张 | ★★★★☆ | ★★★★☆ |
| 安全 | ★★★☆☆ | ★★★★☆ |
| 可靠性/容错 | ★★★★★ | ★★★★★ |
| 性能 | ★★★★☆ | ★★★★★ |
| 分发/部署 | ★★★☆☆ | ★★★★★ |
| 封装/用户体验 | ★☆☆☆☆ | ★★★★★ |
| 测试 | ★★★★★ | ★★★★★ |
| 监控/可观测 | ★★★★☆ | ★★★★★ |
| API 设计 | ★★★☆☆ | ★★★★★ |
| 文档 | ★★★★★ | ★★★★★ |
| 代码质量 | ★★★★☆ | ★★★★★ |
| 法务/合规 | ★★★☆☆ | ★★★☆☆ |
| 竞争格局 | ★★★★☆ | ★★★★☆ |
| **综合** | **★★★★☆** | **★★★★★** |

**一句话：v1.3.1 工程基底稳固。三步走完后，Miser 从"需要 git clone 的黑客工具"变成"下载即用的桌面产品"——安装包 30MB，双击启动，首次自动配置，托盘静默运行。这才是商业化的真正起点：不是代码有多好，是用户有没有理由不用你。**
