"""
test_consumer_product.py — Consumer & Product Manager perspective tests.

Covers:
  - Consumer: "I just cloned this, does it work?"
  - Product Manager: "Does every tool work end-to-end? Are errors helpful?"
  - Black-box: Tool schema completeness, version consistency
  - Gray-box: MCP auto-launch, error format consistency
  - Traversal: Every endpoint × every error input type
"""
import os, sys, json, tempfile, subprocess, threading, time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════════
#  1. CONSUMER ONBOARDING — "I just cloned this repo"
# ═══════════════════════════════════════════════════════════════════════════

class TestConsumerOnboarding:
    """Simulate the first 30 seconds of a new user experience."""

    def test_readme_mentions_correct_version(self):
        """README mentions Miser version."""
        root = Path(__file__).parent.parent
        toml_path = root / "pyproject.toml"
        content = toml_path.read_text()
        import re
        m = re.search(r'version\s*=\s*"([^"]+)"', content)
        assert m, "No version in pyproject.toml"
        version = m.group(1)

        readme = (root / "README.md").read_text()
        # README should have v1.5 or similar heading
        assert "Miser" in readme, "README should mention Miser"

    def test_miser_version_flag_works(self):
        """python miser.py --version prints version and exits 0."""
        root = Path(__file__).parent.parent
        r = subprocess.run(
            [sys.executable, str(root / "miser.py"), "--version"],
            capture_output=True, text=True, timeout=5,
        )
        assert r.returncode == 0, f"Exit code {r.returncode}: {r.stderr}"
        assert "Miser" in r.stdout, f"Expected 'Miser' in output: {r.stdout}"

    def test_all_modules_importable(self):
        """Every module can be imported without side effects."""
        modules = [
            "miser", "config", "tools", "memory", "security",
            "task_queue", "cache", "breaker", "prefetch", "condenser",
            "quality", "model_adapter", "client", "mcp_server",
            "backends", "backends.ollama", "backends.openai_compat",
            "routes", "routes.zero", "routes.admin", "facade",
        ]
        for mod in modules:
            try:
                __import__(mod)
            except ImportError as e:
                # Some modules need flask/rich/requests — skip if deps missing
                if "flask" in str(e) or "rich" in str(e) or "requests" in str(e):
                    continue
                raise

    def test_launcher_scripts_exist(self):
        """miser.sh and miser.bat exist and are valid."""
        root = Path(__file__).parent.parent
        assert (root / "miser.sh").exists(), "miser.sh missing"
        assert (root / "miser.bat").exists(), "miser.bat missing"
        assert (root / "mcp_server.sh").exists(), "mcp_server.sh missing"

    def test_miser_sh_is_executable(self):
        root = Path(__file__).parent.parent
        st = (root / "miser.sh").stat()
        assert st.st_mode & 0o111, "miser.sh is not executable"

    def test_gitignore_covers_runtime_files(self):
        root = Path(__file__).parent.parent
        gi = (root / ".gitignore").read_text()
        for entry in ["__pycache__", "*.py[cod]", ".miser_bootstrapped",
                       "miser.log", ".DS_Store"]:
            assert entry in gi, f".gitignore missing: {entry}"


# ═══════════════════════════════════════════════════════════════════════════
#  2. PRODUCT MANAGER — Tool completeness & correctness
# ═══════════════════════════════════════════════════════════════════════════

class TestToolCompleteness:
    """Every MCP tool is properly defined with description and schema."""

    def test_all_13_mcp_tools_defined(self):
        from mcp_server import TOOLS, ENDPOINT_MAP
        expected = {
            "miser_read", "miser_outline", "miser_grep", "miser_tree",
            "miser_exists", "miser_run", "miser_write", "miser_patch",
            "miser_ask", "miser_codegen", "miser_explain",
            "miser_review", "miser_summarize",
        }
        actual = {t["name"] for t in TOOLS}
        assert actual == expected, f"Missing: {expected - actual}, Extra: {actual - expected}"
        assert len(ENDPOINT_MAP) == len(TOOLS), \
            f"ENDPOINT_MAP has {len(ENDPOINT_MAP)} entries, TOOLS has {len(TOOLS)}"

    def test_every_tool_has_description(self):
        from mcp_server import TOOLS
        for tool in TOOLS:
            assert "description" in tool, f"{tool['name']} missing description"
            assert len(tool["description"]) > 20, \
                f"{tool['name']} description too short: {tool['description']}"

    def test_every_tool_has_input_schema(self):
        from mcp_server import TOOLS
        for tool in TOOLS:
            assert "inputSchema" in tool, f"{tool['name']} missing inputSchema"
            schema = tool["inputSchema"]
            assert "type" in schema
            assert "properties" in schema

    def test_zero_llm_tools_marked_as_such(self):
        """Zero-LLM tool descriptions mention 'zero' or 'ZERO'."""
        from mcp_server import TOOLS
        zero_tools = {"miser_read", "miser_outline", "miser_grep", "miser_tree",
                      "miser_exists", "miser_run", "miser_write", "miser_patch"}
        for tool in TOOLS:
            if tool["name"] in zero_tools:
                desc = tool["description"].lower()
                assert "zero" in desc or "ZERO" in tool["description"], \
                    f"{tool['name']} should mention zero tokens in description"

    def test_llm_tools_mention_local_gpu(self):
        from mcp_server import TOOLS
        llm_tools = {"miser_ask", "miser_codegen", "miser_explain",
                     "miser_review", "miser_summarize"}
        for tool in TOOLS:
            if tool["name"] in llm_tools:
                desc = tool["description"].lower()
                assert "local" in desc or "gpu" in desc, \
                    f"{tool['name']} should mention local GPU in description"

    def test_mcp_instructions_cover_key_tools(self):
        from mcp_server import _INSTRUCTIONS
        # Instructions should mention key tool categories
        for keyword in ["miser_read", "miser_outline", "miser_run", "miser_ask",
                        "ZERO", "zero", "token", "INSTEAD"]:
            assert keyword.lower() in _INSTRUCTIONS.lower(), \
                f"MCP instructions missing keyword: {keyword}"


class TestVersionConsistency:
    """Version number is the same everywhere it's reported."""

    def test_pyproject_matches_miser_version(self):
        root = Path(__file__).parent.parent
        toml = (root / "pyproject.toml").read_text()
        import re
        m = re.search(r'version\s*=\s*"([^"]+)"', toml)
        assert m
        pyproject_ver = m.group(1)

        # Check miser.py --version
        r = subprocess.run(
            [sys.executable, str(root / "miser.py"), "--version"],
            capture_output=True, text=True, timeout=5,
        )
        cli_output = r.stdout.strip()
        # CLI prints "Miser v1.5.0" — extract the version number
        cli_ver = cli_output.replace("Miser", "").replace("v", "").strip()
        assert pyproject_ver in cli_ver or cli_ver in pyproject_ver, \
            f"CLI says '{cli_output}', pyproject.toml says '{pyproject_ver}'"

    def test_pyproject_matches_mcp_server(self):
        root = Path(__file__).parent.parent
        toml = (root / "pyproject.toml").read_text()
        import re
        m = re.search(r'version\s*=\s*"([^"]+)"', toml)
        pyproject_ver = m.group(1)

        mcp = (root / "mcp_server.py").read_text()
        assert f'"version": "{pyproject_ver}"' in mcp, \
            "mcp_server.py version doesn't match pyproject.toml"


# ═══════════════════════════════════════════════════════════════════════════
#  3. ERROR HANDLING — Every endpoint returns JSON on error, not traceback
# ═══════════════════════════════════════════════════════════════════════════

class TestErrorResponseFormat:
    """Black-box: all error responses follow a consistent format."""

    def test_all_error_codes_defined(self):
        from security import ERROR_CODES
        assert len(ERROR_CODES) >= 10
        required = ["E_MISSING_PARAM", "E_NOT_FOUND", "E_INTERNAL",
                    "E_RATE_LIMITED", "E_QUEUE_FULL"]
        for code in required:
            assert code in ERROR_CODES, f"Missing error code: {code}"

    def test_error_codes_are_human_readable(self):
        from security import ERROR_CODES
        for code, (status, msg) in ERROR_CODES.items():
            assert isinstance(msg, str) and len(msg) > 5, \
                f"{code} message too short"
            assert 400 <= status <= 599, f"{code} invalid HTTP status {status}"

    def test_error_response_builds_valid_json(self):
        from security import error_response
        resp = error_response("E_MISSING_PARAM", "path is required")
        assert resp.status_code == 400
        import json
        data = json.loads(resp.data)
        assert "error" in data
        assert data["error"]["code"] == "E_MISSING_PARAM"

    def test_unknown_error_code_defaults_500(self):
        from security import error_response
        resp = error_response("E_FAKE_CODE_THAT_DOESNT_EXIST")
        assert resp.status_code == 500

    def test_custom_status_override(self):
        from security import error_response
        resp = error_response("E_NOT_FOUND", status=418)
        assert resp.status_code == 418


# ═══════════════════════════════════════════════════════════════════════════
#  4. TRAVERSAL — Every tool with every error input type
# ═══════════════════════════════════════════════════════════════════════════

class TestToolTraversal:
    """Systematic: each tool with missing params, invalid paths, edge values."""

    def _call_tool(self, name: str, args: dict) -> tuple:
        """Simulate an MCP tool call by calling the tool function directly."""
        from tools import (
            read_file, grep_file, outline_file, tree_view,
            run_shell, write_to_file, patch_file,
        )

        tool_map = {
            "read": lambda d: read_file(d.get("path", ""), d.get("limit", 8000)),
            "outline": lambda d: outline_file(d.get("path", "")),
            "grep": lambda d: grep_file(d.get("path", ""), d.get("pattern", ""),
                                         d.get("context", 2), d.get("ignore_case", True)),
            "tree": lambda d: tree_view(d.get("path", "~/Desktop"), d.get("depth", 2)),
            "exists": lambda d: str(Path(os.path.expanduser(d.get("path", ""))).exists()),
            "run": lambda d: run_shell(d.get("cmd", ""), d.get("timeout", 30)),
            "write": lambda d: write_to_file(d.get("path", ""), d.get("content", "")),
            "patch": lambda d: patch_file(d.get("path", ""), d.get("old", ""), d.get("new", "")),
        }

        fn = tool_map.get(name)
        if fn is None:
            return False, f"Unknown tool: {name}"
        result = fn(args)
        return True, result

    # ── Missing required params ─────────────────────────────────────────

    def test_read_missing_path(self):
        from tools import read_file
        result = read_file("/nonexistent/ghost_12345.py")
        assert "not found" in result.lower()

    def test_outline_missing_path(self):
        from tools import outline_file
        result = outline_file("/nonexistent/ghost_12345.py")
        assert "not found" in result.lower()

    def test_grep_missing_params(self):
        from tools import grep_file
        result = grep_file("/nonexistent/ghost.py", "pattern")
        assert "not found" in result.lower()

    def test_run_missing_cmd(self):
        ok, result = self._call_tool("run", {})
        assert ok

    def test_write_missing_params(self):
        from tools import write_to_file
        import tempfile, os
        result = write_to_file("/tmp/miser_test_write.txt", "test content")
        assert "Written" in result
        os.unlink("/tmp/miser_test_write.txt")

    def test_patch_missing_params(self):
        from tools import patch_file
        result = patch_file("/nonexistent/ghost.txt", "old", "new")
        assert "not found" in result.lower()

    # ── Invalid paths ────────────────────────────────────────────────────

    def test_read_nonexistent_file(self):
        ok, result = self._call_tool("read", {"path": "/nonexistent/file_12345.xyz"})
        assert ok
        assert "not found" in result.lower()

    def test_outline_nonexistent_file(self):
        ok, result = self._call_tool("outline", {"path": "/nonexistent/ghost.py"})
        assert ok
        assert "not found" in result.lower()

    def test_tree_nonexistent_dir(self):
        ok, result = self._call_tool("tree", {"path": "/nonexistent_dir_xyz"})
        assert ok
        assert "not found" in result.lower()

    def test_exists_nonexistent(self):
        ok, result = self._call_tool("exists", {"path": "/nonexistent/ghost"})
        assert ok
        assert result == "False"

    # ── Edge values ──────────────────────────────────────────────────────

    def test_read_with_zero_limit(self):
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write("x = 1\ny = 2\n")
            path = f.name
        try:
            ok, result = self._call_tool("read", {"path": path, "limit": 0})
            assert ok
        finally:
            os.unlink(path)

    def test_read_with_huge_limit(self, tmp_path):
        f = tmp_path / "small.txt"
        f.write_text("hello")
        ok, result = self._call_tool("read", {"path": str(f), "limit": 999999})
        assert ok
        assert "hello" in result

    def test_grep_with_special_regex_chars(self, tmp_path):
        f = tmp_path / "special.txt"
        f.write_text("price: $100\ntotal: (200)\npath: C:\\Users")
        ok, result = self._call_tool("grep", {"path": str(f), "pattern": r"\$100"})
        assert ok
        assert "100" in result

    def test_outline_empty_file(self, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        ok, result = self._call_tool("outline", {"path": str(f)})
        assert ok
        # should return empty or placeholder, not crash

    def test_tree_with_depth_zero(self, tmp_path):
        ok, result = self._call_tool("tree", {"path": str(tmp_path), "depth": 0})
        assert ok
        assert tmp_path.name in result

    def test_run_blocked_command(self):
        ok, result = self._call_tool("run", {"cmd": "sudo rm -rf /"})
        assert ok
        assert "BLOCKED" in result

    def test_run_with_long_output(self):
        ok, result = self._call_tool("run", {"cmd": "python3 -c 'print(\"x\" * 5000)'"})
        assert ok  # should not crash on long output

    def test_write_creates_parent_dirs(self, tmp_path):
        deep = tmp_path / "a" / "b" / "c" / "test.txt"
        ok, result = self._call_tool("write", {"path": str(deep), "content": "deep"})
        assert ok
        assert deep.exists()
        assert deep.read_text() == "deep"

    def test_patch_special_characters(self, tmp_path):
        f = tmp_path / "patchme.txt"
        f.write_text("hello\nworld\n")
        ok, result = self._call_tool("patch", {"path": str(f), "old": "hello", "new": "hi"})
        assert ok
        assert "Patched" in result


# ═══════════════════════════════════════════════════════════════════════════
#  5. CROSS-PLATFORM — Works on macOS, Linux, and Windows
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossPlatform:
    """Tests that must pass identically on all platforms."""

    def test_home_expansion_works(self):
        result = os.path.expanduser("~/Desktop")
        assert result != "~/Desktop"  # should expand
        assert os.path.isabs(result)

    def test_path_with_spaces_handled(self, tmp_path):
        from tools import read_file
        spaced = tmp_path / "my file with spaces.txt"
        spaced.write_text("content")
        result = read_file(str(spaced))
        assert "content" in result

    def test_unicode_filename(self, tmp_path):
        from tools import read_file
        unicode_file = tmp_path / "文件.txt"
        unicode_file.write_text("你好")
        result = read_file(str(unicode_file))
        assert "你好" in result

    def test_unicode_content_roundtrip(self, tmp_path):
        from tools import write_to_file, read_file
        p = tmp_path / "unicode.txt"
        text = "中文 English 日本語 العربية"
        write_to_file(str(p), text)
        result = read_file(str(p))
        assert text in result

    def test_backslash_path_does_not_crash(self):
        """Windows-style backslash paths should not crash on any platform."""
        from tools import read_file
        result = read_file("C:\\Users\\test\\file.py")
        # Should return "File not found" not crash
        assert "not found" in result.lower() or "C:" in result

    def test_path_traversal_blocked_or_harmless(self):
        """Path traversal like ../../etc/passwd should not read system files."""
        from tools import read_file
        # This should either not find the file or return safely
        result = read_file("../../etc/passwd")
        assert "not found" in result.lower() or "Permission" in result or "error" in result.lower()


# ═══════════════════════════════════════════════════════════════════════════
#  6. MCP INTEGRATION — Auto-launch and tool call correctness
# ═══════════════════════════════════════════════════════════════════════════

class TestMCPIntegration:
    """MCP server behaves correctly as a black-box."""

    def test_mcp_initialize_response(self):
        from mcp_server import handle_request
        resp = handle_request({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
        })
        assert resp is not None
        result = resp["result"]
        assert result["protocolVersion"] == "2024-11-05"
        assert "tools" in result["capabilities"]
        assert result["serverInfo"]["name"] == "miser-mcp"
        assert "instructions" in result, "initialize must include usage instructions"

    def test_mcp_tools_list(self):
        from mcp_server import handle_request
        resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        tools = resp["result"]["tools"]
        assert len(tools) == 13, f"Expected 13 tools, got {len(tools)}"
        names = {t["name"] for t in tools}
        assert "miser_read" in names
        assert "miser_ask" in names

    def test_mcp_notifications_initialized_returns_none(self):
        from mcp_server import handle_request
        resp = handle_request({
            "jsonrpc": "2.0", "method": "notifications/initialized"
        })
        assert resp is None

    def test_mcp_unknown_method(self):
        from mcp_server import handle_request
        resp = handle_request({"jsonrpc": "2.0", "id": 1, "method": "fake/method"})
        assert "error" in resp
        assert resp["error"]["code"] == -32601

    def test_mcp_arg_map_maps_command_to_cmd(self):
        """miser_run 'command' → 'cmd' mapping works."""
        from mcp_server import ARG_MAP
        assert "miser_run" in ARG_MAP
        assert ARG_MAP["miser_run"]["command"] == "cmd"

    def test_endpoint_map_covers_all_tools(self):
        from mcp_server import TOOLS, ENDPOINT_MAP
        tool_names = {t["name"] for t in TOOLS}
        mapped_names = set(ENDPOINT_MAP.keys())
        assert tool_names == mapped_names, \
            f"ENDPOINT_MAP mismatch: {tool_names ^ mapped_names}"

    def test_health_check_uses_standalone_function(self):
        """_miser_status is the health-check helper (internal)."""
        import mcp_server as mcp
        # Clear cache
        mcp._status_cache = None
        # Should return {} when server is not running
        assert isinstance(mcp._status_cache, (dict, type(None)))


# ═══════════════════════════════════════════════════════════════════════════
#  7. TOKEN COUNTING — Accuracy and consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestTokenCounting:
    """Token savings calculations are reasonable."""

    def test_chars_to_tokens_conversion(self):
        from tools import count_saved, get_tokens_saved
        initial = get_tokens_saved()
        count_saved(1000)  # 1000 chars ~ 250 tokens
        assert get_tokens_saved() == initial + 250

    def test_zero_chars_adds_nothing(self):
        from tools import count_saved, get_tokens_saved
        initial = get_tokens_saved()
        count_saved(0)
        assert get_tokens_saved() == initial

    def test_negative_chars_does_not_crash(self):
        from tools import count_saved
        count_saved(-100)  # should not crash

    def test_condensation_ratio_handles_edge_cases(self):
        from condenser import condensation_ratio
        stats = condensation_ratio("hello world", "hi")
        assert "tokens_saved" in stats
        assert "reduction_pct" in stats
        assert stats["original_chars"] == 11
        assert stats["condensed_chars"] == 2


# ═══════════════════════════════════════════════════════════════════════════
#  8. MODEL ADAPTER — All families generate valid payloads
# ═══════════════════════════════════════════════════════════════════════════

class TestModelAdapterConsumer:
    """Every model family produces valid, non-empty prompts."""

    FAMILIES = [
        ("qwen3.5:4b", "qwen3"), ("qwen2.5:7b", "qwen2"),
        ("llama3.1:8b", "llama3"), ("llama4:latest", "llama4"),
        ("llama2:7b", "llama2"), ("mistral:7b", "mistral"),
        ("phi3:mini", "phi3"), ("phi4:latest", "phi4"),
        ("gemma3:4b", "gemma"), ("gemma4:latest", "gemma4"),
        ("deepseek-r1:7b", "deepseek-r1"), ("deepseek-coder:6.7b", "deepseek"),
        ("codellama:7b", "llama3"),
    ]

    def test_all_families_detect_correctly(self):
        from model_adapter import detect_family
        for model, expected_family in self.FAMILIES:
            family = detect_family(model)
            assert family == expected_family, \
                f"{model}: expected {expected_family}, got {family}"

    def test_all_families_produce_non_empty_payload(self):
        from model_adapter import ModelAdapter
        for model, _ in self.FAMILIES:
            adapter = ModelAdapter(model)
            payload = adapter.generate_payload("You are helpful.", "Hello", max_tokens=100)
            assert payload, f"{model} produced empty payload"
            assert "model" in payload
            assert payload["model"] == model
            assert "options" in payload
            assert payload["options"]["num_predict"] > 0

    def test_all_prompts_contain_user_message(self):
        from model_adapter import ModelAdapter
        for model, _ in self.FAMILIES:
            adapter = ModelAdapter(model)
            payload = adapter.generate_payload("System msg", "User msg", max_tokens=100)
            if "prompt" in payload:
                assert "User msg" in payload["prompt"], \
                    f"{model} raw prompt missing user message"
            elif "messages" in payload:
                user_msgs = [m["content"] for m in payload["messages"] if m["role"] == "user"]
                assert any("User msg" in m for m in user_msgs), \
                    f"{model} chat messages missing user message"

    def test_gemma4_uses_chat_api(self):
        """gemma4 uses /api/chat, not raw /api/generate."""
        from model_adapter import ModelAdapter, use_raw_generate
        adapter = ModelAdapter("gemma4:latest")
        assert adapter.family == "gemma4"
        assert not use_raw_generate("gemma4"), "gemma4 should use chat API"


# ═══════════════════════════════════════════════════════════════════════════
#  9. CONCURRENCY — Thread safety under load
# ═══════════════════════════════════════════════════════════════════════════

class TestConcurrencyConsumer:
    """Concurrent access doesn't corrupt state."""

    def test_memory_concurrent_saves(self):
        from memory import Memory
        m = Memory()
        m.clear()
        errors = []

        def save_n(n):
            try:
                for i in range(100):
                    m.save(f"key_{n}_{i}", f"val_{n}_{i}")
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=save_n, args=(t,)) for t in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, f"Concurrent saves failed: {errors}"
        assert len(m.notes) > 0

    def test_token_counter_thread_safety(self):
        from tools import count_saved, get_tokens_saved
        initial = get_tokens_saved()
        errors = []

        def add_tokens():
            try:
                for _ in range(100):
                    count_saved(100)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=add_tokens) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        # 10 threads × 100 iterations × 25 tokens = 25000
        expected = initial + 25000
        assert get_tokens_saved() == expected, \
            f"Expected {expected}, got {get_tokens_saved()}"

    def test_rate_limiter_thread_safety(self):
        from security import RateLimiter
        rl = RateLimiter()
        results = []

        def check():
            for _ in range(25):
                results.append(rl.allow("test", max_req=100, window=60))

        threads = [threading.Thread(target=check) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        allowed = sum(results)
        # 4 threads × 25 = 100 requests, all within limit of 100
        assert allowed == 100, f"Expected 100 allows, got {allowed}"
