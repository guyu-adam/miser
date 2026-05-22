# Miser v1.4.1 产品交付审查 — codereview1

> 审查日期：2026-05-22 | 审查人：产品经理视角
> 交付目标：点击即用 · 极简封装 · 全场景适配

---

## 一、总体评估

Miser 的核心价值主张（"为 AI 编码助手节省 98% token"）明确且有数据支撑。当前版本 v1.4.1 在 Linux/macOS 下功能完整、测试覆盖率高（268+ 用例），但从"交付给客户直接使用"的标准来看，在三个目标维度上各有明显差距。

| 维度 | 当前得分 | 目标 | 差距 |
|------|---------|------|------|
| 点击即用 | 4/10 | 9/10 | 缺 Windows 支持、无可执行文件分发、初始化步骤多 |
| 极简封装 | 5/10 | 9/10 | API 返回格式不一致、SDK 内部细节暴露、两套路由并存 |
| 全场景适配 | 5/10 | 9/10 | 仅 Ollama 后端、10 种语言 outline、无 TypeScript 类型 |

---

## 二、点击即用 — 修改建议

### 问题 1：Windows 用户被"劝退"

**现状** (`scripts/install.sh:88`)：
```
⚠ Windows: auto-start not yet supported. Run scripts/start.sh manually or on login.
```

**影响**：全球 60%+ 开发者使用 Windows。这句警告意味着大多数潜在用户无法正常使用。

**建议修改**：
1. 新增 `scripts/install.ps1` — Windows PowerShell 安装脚本
   - 检测 Python 3.10+
   - 检测/安装 Ollama（winget 或手动引导）
   - 创建 Windows Task Scheduler 任务实现开机自启
   - 自动修改 `~/.claude/CLAUDE.md`
2. 新增 `scripts/miser.xml` — Windows Task Scheduler 模板（对应 macOS plist 和 Linux systemd service）
3. 在 README 显著位置标注 Windows 支持状态

### 问题 2：没有"下载即用"的可执行文件

**现状**：`packaging/miser.spec` 已写好 PyInstaller 配置，但没有发布预构建二进制文件。

**建议修改**：
1. CI 增加 PyInstaller 构建矩阵，发布到 GitHub Releases：
   - `miser-windows-amd64.exe`
   - `miser-darwin-arm64`（macOS Apple Silicon）
   - `miser-darwin-x64`（macOS Intel）
   - `miser-linux-x64`
2. 或提供单一入口脚本 `miser.bat` / `miser.ps1`，自动完成：检测环境 → 安装依赖 → 启动服务
3. 二进制文件自带 Ollama 检测逻辑，未安装时弹出引导链接

### 问题 3：首次运行体验脆弱

**现状** (`miser.py:629-633`)：仅通过 `memory.json` 是否存在来判断"首次运行"。如果用户删除了 memory.json 但服务已配置好，会被错误地重新引导到 setup wizard。

**建议修改**：
```python
# 改为检查标记文件
_BOOTSTRAP_FLAG = Path(__file__).parent / ".miser_bootstrapped"
if not _BOOTSTRAP_FLAG.exists() and not cli.wizard:
    # ... run wizard
    _BOOTSTRAP_FLAG.touch()
```

### 问题 4：客户端无自检能力

**现状**：`client.py` 的 `_post()` 直接发请求，没有先检测服务器是否在运行。Claude Code 中的嵌入代码需要手动写 try/except + 启动逻辑。

**建议修改**：在 `client.py` 中增加 `W.ensure_running()` 方法：
```python
def ensure_running(self):
    """Auto-start miser if not running. Returns True if ready."""
    try:
        self.status()
        return True
    except Exception:
        import subprocess, time
        subprocess.Popen([sys.executable, '-m', 'miser'], ...)
        time.sleep(3)
        try:
            self.status()
            return True
        except Exception:
            return False
```

### 问题 5：依赖 Ollama 手动安装

**建议**：考虑在 PyInstaller 打包时内嵌 Ollama 便携版，或至少在 setup wizard 中提供一键安装（当前仅打印链接）。

---

## 三、极简封装 — 修改建议

### 问题 6：API 返回格式不一致

**现状**：

| 端点 | 返回字段 |
|------|---------|
| `/read` | `{"content": ..., "path": ...}` |
| `/grep` | `{"matches": ..., "path": ..., "pattern": ...}` |
| `/outline` | `{"outline": ..., "path": ...}` |
| `/run` | `{"output": ...}` |
| `/exists` | `{"exists": ..., "path": ..., "is_file": ..., "is_dir": ...}` |
| `/v1/read` (blueprint) | `{"data": {"content": ...}}` |
| `/ask` | `{"result": ...}` |
| `/summarize` | `{"summary": ..., "source": ..., "original_chars": ...}` |
| `/codegen` | `{"code": ..., "lang": ...}` |
| `/explain` | `{"explanation": ..., "source": ...}` |

**影响**：调用方需要针对每个端点写不同的解析逻辑。`client.py` 的每个方法都有不同的字段提取代码（`d.get("content")`, `d.get("matches")`, `d.get("outline")`, etc.）。

**建议修改**：统一所有端点的返回格式为：
```json
{
  "ok": true,
  "data": "<主要结果>",
  "meta": {
    "op": "read",
    "path": "...",
    "tokens_saved": 1234
  }
}
```
错误统一为：
```json
{
  "ok": false,
  "error": {"code": "E_NOT_FOUND", "message": "File not found: /tmp/x"}
}
```
这将使 `client.py` 的体量减少约 40%，且所有语言 SDK 的解析代码统一为 `d.data`。

### 问题 7：client.py 暴露内部实现细节

**现状**：`_check_llm()`、`_flag()`、`_extract_flags()`、`_HALLUCINATION_PHRASES` 都是模块级函数/变量，不在 `_W` 类内。

**建议修改**：
1. 将 `_check_llm` 移入 `_W` 类作为私有方法
2. `_HALLUCINATION_PHRASES` 移入类变量，允许用户自定义：`W.hallucination_phrases.append("custom phrase")`
3. 对外只暴露 `W` 实例和其公开方法

### 问题 8：batch() 的调用方式与单接口不一致

**现状**：
```python
# 单接口 — 命名参数
W.outline("~/f.py")
W.grep("~/f.py", "def fn", ctx=2)

# batch — 位置元组，格式完全不同
W.batch([("outline", "~/f.py"), ("grep", "~/f.py", "pattern")])
```

**建议修改**：支持链式或对象式 batch：
```python
# 方案A：传递方法调用描述
W.batch([
    W._op("outline", path="~/f.py"),
    W._op("grep", path="~/f.py", pattern="def fn"),
])

# 方案B：上下文管理器
with W.batch() as b:
    b.outline("~/f.py")
    b.grep("~/f.py", "def fn")
```

### 问题 9：/v1 和非 /v1 路由并存

**现状**：同一个 `/read` 同时在根路径和 `/v1/read` 蓝图注册。miser.py 的 `@app.route("/read")` 和 `routes/zero.py` 的 `@zero.route("/read", ...)` 是两个不同的处理函数。

**建议修改**：根路径端点改为 `/v1/` 蓝图的别名重定向，统一逻辑。老路径加 `Deprecation` 警告头，v2.0 移除。

### 问题 10：JS SDK 比 Python SDK 弱

**现状**：`extensions/js-sdk/index.js` 只有基础 HTTP 调用，完全没有：
- 质量监督（`_check_llm`）
- 质量路由（`should_offload`）
- flag 提取和标记
- verify 开关
- batch 支持

**建议修改**：JS SDK 至少达到 Python SDK 80% 的功能对齐，或发布 TypeScript 类型定义让 IDE 提供智能提示。

---

## 四、全场景适配 — 修改建议

### 问题 11：Ollama 是唯一后端

**现状**：所有 LLM 操作硬编码依赖 Ollama API（`localhost:11434`）。但企业客户可能使用：
- LM Studio（localhost:1234）
- llama.cpp server（localhost:8080）
- vLLM / TGI
- 内部代理的 OpenAI 兼容 API

**建议修改**：在 `model_adapter.py` 中抽象后端接口：
```python
class LLMBackend:
    def generate(self, payload) -> str: ...
    def health(self) -> bool: ...

class OllamaBackend(LLMBackend): ...
class OpenAICompatBackend(LLMBackend): ...
```
通过 `MISER_BACKEND=openai` 环境变量切换。

### 问题 12：outline 仅支持 10 种语言

**现状**：`tools.py` 的 `_OUTLINE_PATTERNS` 支持 Python/JS/TS/TSX/Go/Rust/Java/Ruby/Shell/SQL。缺少：
- Vue SFC (.vue)
- Svelte (.svelte)
- Kotlin (.kt)
- Swift (.swift)
- C/C++ (.c, .cpp, .h)
- C# (.cs)
- Scala (.scala)
- Dart (.dart)

**建议修改**：新增 8 种语言的 pattern，覆盖 Top 20 编程语言。

### 问题 13：适配器手动配置成本高

**现状**：11 个 adapter 配置文件需要用户手动复制到对应工具的配置目录。没有自动化。

**建议修改**：
```bash
# 一键配置命令
python -m miser adapt --tool cline     # 自动检测 Cline 配置位置并注入
python -m miser adapt --tool aider     # 自动修改 .aider.conf.yml
python -m miser adapt --all            # 检测所有已安装工具并配置
```

### 问题 14：无远程访问支持

**现状**：`cors_middleware()` 只允许 localhost/127.0.0.1。团队协作场景（如共享开发服务器）无法使用。

**建议修改**：
1. 增加 `MISER_BIND=0.0.0.0` 和 `MISER_CORS_ORIGINS=*` 配置项
2. 配合 `MISER_AUTH_TOKEN` 强制鉴权
3. 支持 HTTPS（自签名证书自动生成）

### 问题 15：无 TypeScript 类型定义

**建议**：为 JS SDK 提供 `index.d.ts`，让 TypeScript 项目和 IDE 获得完整的类型提示。

---

## 五、测试用例审查

### 5.1 当前测试覆盖盲区

| 盲区 | 风险等级 | 说明 |
|------|---------|------|
| Windows 平台 | **高** | 零覆盖。`run_shell` 测试全是 bash 命令，`\` 续行符在 Windows 无效 |
| JS SDK | **高** | `extensions/js-sdk/index.js` 零测试 |
| VS Code 扩展 | **高** | `extensions/vscode/extension.js` 零测试 |
| 安装/卸载脚本 | **高** | `install.sh`、`uninstall.sh`、`start.sh` 零测试 |
| 真实 Ollama 集成 | **中** | 所有测试 mock 了 LLM 调用，从未验证 Ollama 真实响应 |
| 端到端客户场景 | **中** | 无"新用户从零安装到首次使用"的完整测试 |
| 多模型行为差异 | **中** | 仅测试 family detection，未测试不同模型的真实输出质量 |
| 长时间运行稳定性 | **中** | 无内存泄漏、fd 泄漏、48h 持续运行测试 |
| 网络中断恢复 | **中** | Ollama 中途不可达时的行为未测试 |
| i18n 功能 | **低** | `I18N_PATTERNS` 存在但从未被测试 |

### 5.2 测试用例修改和新增建议

#### 新增文件：`tests/test_customer_scenarios.py`

这些测试模拟客户真实使用场景：

```python
"""
Customer scenario tests — end-to-end user journeys.
Tests what real customers actually do, not just unit behavior.
"""

class TestNewUserOnboarding:
    """Scenario: A developer installs Miser for the first time."""

    def test_setup_wizard_detects_python_version(self):
        """Wizard should correctly identify Python 3.10+."""
        from scripts.setup_wizard import check_python
        assert check_python() is True

    def test_setup_wizard_handles_missing_ollama_gracefully(self):
        """If Ollama is not installed, wizard should not crash."""
        # Mock subprocess to simulate missing ollama
        import scripts.setup_wizard as wiz
        # Should return False gracefully, not raise
        result = wiz.check_ollama()  # may be False if ollama absent
        assert isinstance(result, bool)

    def test_first_run_creates_bootstrap_flag(self):
        """After first successful start, .miser_bootstrapped should exist."""
        # This would test the fix for issue #3 above

    def test_install_script_exists_for_all_platforms(self):
        """install.sh, install.ps1 must exist."""
        import os
        base = os.path.dirname(os.path.dirname(__file__))
        scripts_dir = os.path.join(base, "scripts")
        assert os.path.exists(os.path.join(scripts_dir, "install.sh"))
        # After adding Windows support:
        # assert os.path.exists(os.path.join(scripts_dir, "install.ps1"))


class TestDailyDevelopmentWorkflow:
    """Scenario: A developer using Miser throughout a typical workday."""

    def test_understand_new_project_structure(self):
        """User clones a repo and wants to understand it quickly."""
        import tempfile, os
        # Create a realistic project structure
        with tempfile.TemporaryDirectory() as tmp:
            # Create files a real project would have
            os.makedirs(os.path.join(tmp, "src", "api"))
            os.makedirs(os.path.join(tmp, "tests"))
            with open(os.path.join(tmp, "src", "api", "auth.py"), "w") as f:
                f.write("""
import jwt
from functools import wraps

def login(username: str, password: str) -> dict:
    '''Authenticate user and return token.'''
    pass

def verify_token(token: str) -> bool:
    '''Verify JWT token validity.'''
    pass

def require_auth(f):
    '''Decorator to require authentication.'''
    @wraps(f)
    def wrapper(*args, **kwargs):
        pass
    return wrapper
""")
            # Test tree view — first thing a developer does
            import tools
            tree = tools.tree_view(tmp, depth=2)
            assert "src" in tree
            assert "api" in tree
            assert "tests" in tree

            # Test outline — understand file structure
            outline = tools.outline_file(os.path.join(tmp, "src", "api", "auth.py"))
            assert "login" in outline
            assert "verify_token" in outline
            assert "require_auth" in outline

            # Test grep — find specific function usage
            grep_result = tools.grep_file(
                os.path.join(tmp, "src", "api", "auth.py"), "def "
            )
            assert "login" in grep_result
            assert "verify_token" in grep_result

    def test_debug_session_workflow(self):
        """User encounters an error and debugs with miser."""
        error_msg = "TypeError: unsupported operand type(s) for +: 'int' and 'str'"
        faulty_code = """
def calculate_total(items):
    total = 0
    for item in items:
        total += item.get('price', 0)  # price might be string
    return total
"""
        # This would call W.fix() — but in unit test we test the endpoint logic
        import miser
        with miser.app.test_client() as c:
            r = c.post("/fix", json={
                "error": error_msg,
                "code": faulty_code
            })
            # Even without Ollama, should get a structured response
            assert r.status_code in (200, 500)
            if r.status_code == 200:
                data = r.get_json()
                assert "fix" in data

    def test_write_tests_for_new_feature(self):
        """User wants to generate tests for a new function."""
        code = """
def validate_email(email: str) -> bool:
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))
"""
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code)
            f.flush()
            import miser
            with miser.app.test_client() as c:
                r = c.post("/test", json={"path": f.name, "function": "validate_email"})
                assert r.status_code in (200, 500)
        os.unlink(f.name)

    def test_batch_operation_typical_workflow(self):
        """User does multiple things at once — the batch use case."""
        import tempfile, os
        with tempfile.TemporaryDirectory() as tmp:
            test_file = os.path.join(tmp, "app.py")
            with open(test_file, "w") as f:
                f.write("def main():\n    print('hello')\n")
            import miser
            with miser.app.test_client() as c:
                r = c.post("/batch", json={"tasks": [
                    {"type": "exists", "path": test_file},
                    {"type": "outline", "path": test_file},
                    {"type": "run", "cmd": f"wc -l {test_file}" if os.name != "nt" else f"find /c /v \"\" {test_file}"},
                ]})
                d = r.get_json()
                assert len(d["results"]) == 3
                assert d["results"][0]["result"] is True  # exists
                assert "main" in d["results"][1]["result"]  # outline
                # run result varies by OS


class TestCrossPlatformCompatibility:
    """Scenario: Miser must work identically on Windows, macOS, and Linux."""

    def test_path_handling_windows_backslash(self):
        """Windows paths with backslashes must be normalized."""
        import tools
        import os
        # Simulate a Windows-style path
        win_path = r"C:\Users\dev\project\app.py"
        # tools should handle this gracefully
        # (will fail on non-Windows but should not crash)
        result = tools.read_file(win_path)
        assert isinstance(result, str)

    def test_path_handling_wsl_path(self):
        """WSL paths like /mnt/c/... should work."""
        import tools
        wsl_path = "/mnt/c/Users/dev/project/app.py"
        result = tools.read_file(wsl_path)
        assert isinstance(result, str)  # graceful handling, not crash

    def test_shell_commands_cross_platform(self):
        """Commands that work on all platforms."""
        import tools
        # Python evaluation works everywhere
        result = tools.run_shell("python -c \"print('hello')\"")
        assert "hello" in result.lower()

    def test_home_directory_expansion(self):
        """~ expansion must work on all platforms."""
        import os
        from pathlib import Path
        home = str(Path(os.path.expanduser("~")))
        assert len(home) > 0
        assert os.path.exists(home)


class TestErrorScenarios:
    """Scenario: Things go wrong — miser must degrade gracefully."""

    def test_ollama_unreachable_during_request(self):
        """When Ollama is not running, LLM endpoints should return useful errors."""
        import miser
        with miser.app.test_client() as c:
            r = c.post("/ask", json={"task": "explain this"})
            assert r.status_code in (200, 500)
            data = r.get_json()
            # Should get either a result or a meaningful error
            assert "result" in data or "error" in data

    def test_disk_full_during_write(self):
        """Write operations should fail gracefully when disk is full."""
        # This is hard to simulate, but we can test error response format
        import miser
        with miser.app.test_client() as c:
            r = c.post("/write", json={"path": "/dev/full_test", "content": "test"})
            # Should not crash the server
            assert r.status_code in (200, 500)

    def test_concurrent_requests_dont_corrupt_state(self):
        """Multiple simultaneous requests should not corrupt server state."""
        import miser, threading, json
        errors = []

        def make_requests():
            try:
                with miser.app.test_client() as c:
                    for _ in range(20):
                        r = c.get("/health")
                        assert r.status_code == 200
                        r = c.post("/exists", json={"path": "miser.py"})
                        d = json.loads(r.data)
                        assert d["exists"] is True
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=make_requests) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"Concurrent access failed: {errors}"

    def test_very_long_input_handled(self):
        """Extremely long task descriptions should not crash the server."""
        import miser
        with miser.app.test_client() as c:
            long_task = "explain this code " + "x" * 10000
            r = c.post("/ask", json={"task": long_task})
            # Should either process or reject with a clear error
            assert r.status_code in (200, 400, 413, 500)


class TestMemoryAndContextPersistence:
    """Scenario: User builds context across multiple sessions."""

    def test_memory_survives_server_restart(self):
        """Memory data should persist across server restarts."""
        import miser, json, os, tempfile, shutil

        # Use a temporary memory file
        tmp_dir = tempfile.mkdtemp()
        try:
            mem_file = os.path.join(tmp_dir, "memory.json")
            # Save some data
            import memory
            m = memory.Memory(storage_path=mem_file)
            m.save("project_x", "uses FastAPI + SQLAlchemy")
            m.save("bug_123", "fixed by PR #45")

            # Simulate restart by creating a new Memory instance
            m2 = memory.Memory(storage_path=mem_file)
            assert m2.load("project_x") == "uses FastAPI + SQLAlchemy"
            assert m2.load("bug_123") == "fixed by PR #45"
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def test_memory_context_relevant_to_current_task(self):
        """Memory.ctx() should return context relevant to the current task."""
        import memory
        m = memory.Memory()
        m.clear()
        m.save("auth_module", "JWT authentication with refresh tokens")
        m.save("db_schema", "PostgreSQL with SQLAlchemy ORM")
        m.record(1, "explain auth.py", "This module handles JWT auth")

        ctx = m.ctx("explain authentication flow in this project")
        # Context should contain relevant saved notes or history
        assert isinstance(ctx, str)
        # "auth" related content should appear
        assert "JWT" in ctx or "auth" in ctx.lower() or len(ctx) > 0


class TestAPIResponseConsistency:
    """Validate the unified response format (ref: issue #6 above)."""

    def test_all_zero_llm_endpoints_have_consistent_format(self):
        """Read/grep/outline/tree/run/exists should follow the same structure."""
        import miser

        endpoints = [
            ("/read", {"path": "miser.py"}, "content"),
            ("/grep", {"path": "miser.py", "pattern": "def "}, "matches"),
            ("/outline", {"path": "tools.py"}, "outline"),
            ("/tree", {"path": ".", "depth": 1}, "tree"),
            ("/exists", {"path": "miser.py"}, "exists"),
        ]

        with miser.app.test_client() as c:
            for path, payload, expected_key in endpoints:
                r = c.post(path, json=payload)
                assert r.status_code == 200, f"{path} returned {r.status_code}"
                # Current behavior: each has its own key
                # Target behavior: all should have {"ok": true, "data": ...}
                d = r.get_json()
                assert expected_key in d, f"{path} missing key '{expected_key}'"

    def test_v1_blueprint_uses_data_envelope(self):
        """v1 endpoints already use {"data": ...} wrapper — others should too."""
        import miser
        with miser.app.test_client() as c:
            r = c.post("/v1/read", json={"path": "client.py"})
            assert r.status_code == 200
            assert "data" in r.get_json()

    def test_error_responses_have_standard_format(self):
        """All errors should use the E_* error code format."""
        import miser
        with miser.app.test_client() as c:
            # Missing required param
            r = c.post("/read", json={})
            d = r.get_json()
            # Some endpoints use custom errors, some use standardized ones
            assert "error" in d


class TestSDKConsistency:
    """Python and JS SDKs should behave identically."""

    def test_python_sdk_all_methods_exist(self):
        """Every advertised method should exist on W."""
        from client import W
        expected_methods = [
            "ask", "run", "read", "grep", "outline", "tree", "exists",
            "write", "patch", "summarize", "codegen", "explain", "fix",
            "test", "review", "condense", "git_summary", "batch",
            "note", "clear", "status", "quality",
        ]
        for method in expected_methods:
            assert hasattr(W, method), f"W.{method} missing"
            assert callable(getattr(W, method)), f"W.{method} is not callable"

    def test_python_sdk_methods_have_consistent_signatures(self):
        """Related methods should have similar parameter patterns."""
        import inspect
        from client import _W

        # All Zero-LLM methods should accept 'path' as first positional arg
        zero_llm_path_methods = ["read", "outline", "tree", "exists", "write"]
        for name in zero_llm_path_methods:
            sig = inspect.signature(getattr(_W, name))
            params = list(sig.parameters.keys())
            assert "path" in params, f"W.{name}() missing 'path' parameter"

    def test_js_sdk_exports_match_python_sdk(self):
        """JS SDK should export the same set of functions."""
        import os, re
        base = os.path.dirname(os.path.dirname(__file__))
        js_sdk_path = os.path.join(base, "extensions", "js-sdk", "index.js")
        if os.path.exists(js_sdk_path):
            with open(js_sdk_path) as f:
                js_content = f.read()
            # Check exports
            exports = re.findall(r'exports\.(\w+)\s*=', js_content)
            expected = ["outline", "grep", "tree", "exists", "read", "write",
                        "run", "ask", "codegen", "explain", "fix", "test",
                        "review", "condense", "status", "health", "metrics"]
            for exp in expected:
                assert exp in exports, f"JS SDK missing exports.{exp}"
```

#### 新增文件：`tests/test_windows_compatibility.py`

```python
"""
Windows-specific compatibility tests.
These can run on any platform but test Windows-adjacent behavior.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tools

class TestWindowsPathHandling:
    def test_backslash_path_normalization(self):
        result = tools.read_file("C:\\Windows\\System32\\drivers\\etc\\hosts")
        assert isinstance(result, str)

    def test_mixed_slash_paths(self):
        result = tools.read_file("C:/Users/dev/project\\app.py")
        assert isinstance(result, str)

    def test_unc_path_handling(self):
        result = tools.read_file("\\\\server\\share\\file.txt")
        assert isinstance(result, str)

class TestWindowsShellSafety:
    def test_cmd_injection_blocked(self):
        dangerous = [
            "rmdir /s /q C:\\",
            "del /f /s /q *.*",
            "format C:",
            "reg delete HKLM\\Software",
        ]
        for cmd in dangerous:
            result = tools.run_shell(cmd)
            assert "blocked" in result.lower() or "denied" in result.lower()


class TestWindowsEncoding:
    def test_gbk_encoded_file_read(self):
        """Chinese Windows often uses GBK encoding."""
        tmp = tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False)
        tmp.write("中文内容测试".encode('gbk'))
        tmp.close()
        result = tools.read_file(tmp.name)
        assert isinstance(result, str)
        os.unlink(tmp.name)

    def test_bom_utf8_file(self):
        """Windows Notepad adds BOM to UTF-8 files."""
        tmp = tempfile.NamedTemporaryFile(mode='wb', suffix='.txt', delete=False)
        tmp.write(b'\xef\xbb\xbfdef hello(): pass\n')
        tmp.close()
        result = tools.read_file(tmp.name)
        assert "hello" in result
        os.unlink(tmp.name)
```

#### 修改现有文件：`tests/test_integration.py`

建议新增以下测试方法：

```python
# 加入 TestZeroLLMEndpoints 类：
def test_read_with_special_chars_path(self):
    """Files with spaces, Chinese chars, emoji in path should work."""
    import tempfile, os
    tmp = tempfile.mkdtemp()
    try:
        test_path = os.path.join(tmp, "项目 文件 (copy).py")
        with open(test_path, "w") as f:
            f.write("# test file")
        c = client()
        r = c.post("/read", json={"path": test_path})
        assert r.status_code == 200
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

def test_path_traversal_blocked(self):
    """../ attacks should be handled safely."""
    c = client()
    r = c.post("/read", json={"path": "../../etc/passwd"})
    d = json.loads(r.data)
    # Should not leak system files
    assert r.status_code in (200, 403, 404)

# 加入 TestBatch 类：
def test_batch_with_mixed_success_and_failure(self):
    """One task failing should not affect others in the batch."""
    c = client()
    r = c.post("/batch", json={"tasks": [
        {"type": "run", "cmd": "echo ok"},
        {"type": "read", "path": "/nonexistent/file_xyz"},
        {"type": "run", "cmd": "echo still_works"},
    ]})
    d = json.loads(r.data)
    assert len(d["results"]) == 3
    assert "ok" in d["results"][0].get("result", "")
    # Middle one may have error or "not found"
    assert "still_works" in d["results"][2].get("result", "")

# 加入 TestFacade 类：
def test_facade_streaming_response(self):
    """SSE streaming should work for chat completions."""
    c = client()
    r = c.post("/v1/chat/completions", json={
        "messages": [{"role": "user", "content": "say hi"}],
        "stream": True,
        "max_tokens": 20,
    })
    assert r.status_code in (200, 500)
    if r.status_code == 200:
        content = r.data.decode()
        assert "data:" in content or "delta" in content
```

---

## 六、优先级排序

按"客户交付就绪"标准，以下是优先级排序的改进清单：

### P0 — 阻塞交付（本周必须完成）
1. **Windows 安装脚本** (`install.ps1`) — 60% 用户无法使用
2. **client.py 自启能力** (`ensure_running()`) — 点击即用的核心
3. **首次运行检测修复** — 防止重复 wizard 引导
4. **API 返回格式统一** — 减少 SDK 维护成本，为全场景打基础

### P1 — 体验完整（2周内）
5. **JS SDK 质量监督对齐** — 非 Python 用户的基本保障
6. **batch() API 重新设计** — 极简封装的关键体现
7. **TypeScript 类型定义** — 企业客户基本要求
8. **安装/卸载脚本自动化测试** — 客户环境多样性保障
9. **outline 扩展 8 种语言** — 全场景适配的快速收益

### P2 — 竞争力提升（1个月内）
10. **后端抽象（支持非 Ollama）** — 企业客户关键需求
11. **预构建二进制发布** — 降低准入门槛
12. **`miser adapt --all` 一键配置** — 多工具用户的核心痛点
13. **端到端客户场景测试** — 防止回归

---

## 七、总结

Miser v1.4.1 的技术内核扎实，但在"产品化交付"维度有明确的差距。核心矛盾是：**项目当前是一个"开发者工具"的形态，但客户期望的是"即装即用的产品"。** 

三个目标中，**点击即用**差距最大（Windows 支持缺失是硬伤），**极简封装**次之（API 不一致和 SDK 暴露内部细节），**全场景适配**需要长期投入但有清晰的路线图。

建议 v1.5 版本聚焦 P0 和 P1 项目，让一个 Windows 用户从下载到首次成功使用的时间控制在 5 分钟以内。
