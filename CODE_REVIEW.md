# Miser v1.1 — Code Review

**Reviewer:** @guyu-adam
**Date:** 2026-05-21
**Repository:** guyu-adam/miser

---

## Overall Assessment

v1.0 → v1.1 是一个扎实的迭代。所有 12 个原始问题已修复。新增的 `quality.py` / `adaptive.py` / `condenser.py` / `prefetch.py` 方向正确，但带来了新的工程债务。项目目前处于**可用的个人工具**水平，距离生产级还有距离。

| Dimension | v1.1 Rating | v1.0 Rating | Change |
|-----------|------------|-------------|--------|
| Concept/Value | ★★★★★ | ★★★★★ | — |
| Security | ★★★★☆ | ★★☆☆☆ | `eval()` → AST, `shell=True` → 安全拦截, AUTH_TOKEN |
| Maintainability | ★★★★☆ | ★★★☆☆ | 文件拆分 1→3, 新增模块 4 个 |
| Engineering Completeness | ★★★☆☆ | ★★★★☆ | 新模块带来新问题, test 目录缺失 |

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

## New Critical Issues

### 13. 没有 `tests/` 目录 — 测试不可复现

`TEST_REPORT.md` 声称 62/62 测试通过，但仓库中没有任何测试文件。没有 `tests/` 目录、没有 `pytest` 配置、没有 CI。这份报告无法验证。

```
$ ls tests/
ls: cannot access 'tests/': No such file or directory
```

**建议:** 把测试代码放入 `tests/` 目录，添加 `pytest` 配置和 GitHub Actions。

### 14. `outline_file` 只支持 Python — 核心功能对多语言项目失效

`tools.py` 的 `outline_file()` 用正则匹配 `def ` 和 `class ` 提取函数签名。JS/TS/Go/Rust 项目用不了这个核心卖点（"省 94% token"）。

**建议:** 按扩展名分派解析器，至少先支持 `function` / `fn` / `func` / `=>` 模式。

### 15. 零 Windows 支持

`install.sh` 是 bash 脚本，service 文件只提供了 `systemd` 和 `launchd`。Windows 用户只能手动 `python miser.py`。连 README 都没提 Windows。

**建议:** 至少加一个 `install.ps1` 和 Windows Service wrapper，或者在 README 里写清楚 Windows 手动启动步骤。

---

## New Medium Issues

### 16. 没有配置系统

全部靠环境变量 (`MISER_MODEL`, `MISER_AUTH_TOKEN`)。端口号 7860 硬编码在 `miser.py:578`。没有 `.env` 文件加载、没有 `config.yaml`、没有 CLI 参数。

**建议:** 加 `pyproject.toml` 或 `.env` 文件支持，端口改为可配置。

### 17. 不能 `pip install`

没有 `setup.py` / `pyproject.toml`，用户必须 clone 源码然后手动 `sys.path.insert`。

```python
import sys; sys.path.insert(0, '/path/to/miser')  # 当前唯一安装方式
from client import W
```

**建议:** 加 `pyproject.toml`，至少支持 `pip install -e .` 可编辑安装。

### 18. 日志系统缺失

全部输出靠 `rich.console` 打印到终端。后台运行时（systemd service）没有任何 structured logging，出问题无法排查。

**建议:** 至少加 `logging` 模块输出到 `~/.miser/miser.log`。

### 19. `prefetch.py` 命中率统计是假的

```python
# prefetch.py:94-98
def check_hit(self, filepath: str) -> bool:
    with self._lock:
        if filepath in self._access_order:  # 只要访问过就算"命中"
            self._hit_count += 1
```

不管文件是不是 prefetch 预加载的，只要在访问历史里出现过就算 hit。这个计数器不衡量 prefetch 的实际效果。

**建议:** 改为用 `os.mincore()`（Linux）或对比访问时间戳来判断是否真正由 prefetch 加载。

### 20. `condenser.py` 硬截断 + 无重试

```python
# condenser.py:101
prompt = f"{template}\n\n---CONTENT---\n{content[:8000]}\n---END---"
```

超过 8000 字符的内容尾部直接丢弃。`distill()` 失败时静默返回原文，没有 retry。

**建议:** 对长文本分块蒸馏后合并；失败时至少 retry 一次。

### 21. Token 计数是估算值，不是真实 tokenizer 输出

```python
# tools.py — 核心计数逻辑
count_saved(len(result) * 3)
count_saved(len(content) // 4)
```

用字符数除以 4 估 token，与实际 tokenizer（tiktoken / HuggingFace tokenizer）输出有明显偏差。所有 benchmark 数字都基于这个估算法，包括 README 里的 98.7%。

**建议:** 集成 `tiktoken` 做精确计数，至少在 benchmark 报告中标注是估算值。README 里 "18,880 tokens saved" 应该写 "~18,880 tokens saved (estimated)"。

---

## 架构层面的观察

### 模块数量增长过快

v1.0 只有 `miser.py` + `client.py` + `model_adapter.py` 三个核心文件。v1.1 增加了 6 个新文件（`tools.py`, `memory.py`, `quality.py`, `adaptive.py`, `condenser.py`, `prefetch.py`），但模块之间的依赖是散乱的 import，没有统一的插件注册机制。

`miser.py` 现在 609 行（比 v1.0 的 726 行好转），但仍然是 God module — 所有 Flask 路由都在这里，import 了几乎所有模块。

### `quality.py` / `adaptive.py` 的分工重叠

两个模块都做"是否应该 offload"的判断，但 `quality.py` 是静态关键词白名单，`adaptive.py` 是动态成功率学习。`client.py` 里 `should_offload()` 和 `_router.should_route_to_local()` 分别调用两者，没有一个统一的 routing pipeline。

**建议:** 合并为一个 `Router` 类，静态规则 → 动态规则 → 最终决策，单一入口。

---

## What's Well Done

- **`model_adapter.py`** — 多模型适配层仍然是最扎实的模块，17 个模型家族的 prompt 格式化 + response 清洗，三层分离干净。
- **`client.py` 监督层** — 幻觉检测、语法验证、上下文匹配三重检查，设计合理。
- **`adaptive.py` 的递增冷却** — 连续失败 → 冷却时间翻倍的思路好，承认本地模型不可靠并做降级，这比假装模型完美要诚实得多。
- **`quality.py` 的 CRITICAL 白名单** — auth/payment/deploy 永不分流到本地 4B 模型，安全底线清晰。
- **Zero-LLM / Local-LLM 两层拆分** — 核心架构正确，正则操作为主、LLM 为辅的定位是对的。

---

## Summary

v1.0 的 12 个问题全部修完，工程质量有明显提升。当前最大的三个短板：

1. **没有测试文件** — `TEST_REPORT.md` 不可复现，这是最致命的问题
2. **`outline_file` 只支持 Python** — 核心功能覆盖面太窄
3. **无法 `pip install` + 零 Windows 支持** — 分发和上手门槛高

这三个修完后，项目从"个人工具"进到"社区可用"级别。其余问题（日志、配置、prefetch 统计）可以排后。
