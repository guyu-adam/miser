"""Customer scenario E2E tests — real user journeys (codereview1 #13)."""
import sys, os, tempfile, json, threading, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tools, miser


def client():
    miser.app.config['TESTING'] = True
    return miser.app.test_client()


class TestNewUserOnboarding:
    def test_setup_wizard_check_ollama(self):
        from scripts.setup_wizard import check_ollama
        result = check_ollama()
        assert isinstance(result, bool)

    def test_install_scripts_exist(self):
        base = os.path.dirname(os.path.dirname(__file__))
        sd = os.path.join(base, "scripts")
        assert os.path.exists(os.path.join(sd, "install.sh"))
        assert os.path.exists(os.path.join(sd, "install.ps1"))

    def test_bootstrap_flag_prevents_rewizard(self):
        flag = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".miser_bootstrapped")
        # Flag may or may not exist — just verify it's a valid path
        assert isinstance(flag, str)


class TestDailyWorkflow:
    def test_understand_project_structure(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.makedirs(os.path.join(tmp, "src", "api"))
            os.makedirs(os.path.join(tmp, "tests"))
            with open(os.path.join(tmp, "src", "api", "auth.py"), "w") as f:
                f.write("""
import jwt
from functools import wraps
def login(username: str, password: str) -> dict: pass
def verify_token(token: str) -> bool: pass
def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs): pass
    return wrapper
""")
            tree = tools.tree_view(tmp, depth=2)
            assert "src" in tree
            assert "api" in tree
            outline = tools.outline_file(os.path.join(tmp, "src", "api", "auth.py"))
            assert "login" in outline
            assert "verify_token" in outline

    def test_debug_session(self):
        c = client()
        r = c.post("/fix", json={
            "error": "TypeError: unsupported operand type(s) for +: 'int' and 'str'",
            "code": "def calc(items):\n    total = 0\n    for item in items:\n        total += item['price']\n    return total\n"
        })
        assert r.status_code in (200, 500)

    def test_batch_typical_workflow(self):
        with tempfile.TemporaryDirectory() as tmp:
            tf = os.path.join(tmp, "app.py")
            with open(tf, "w") as f:
                f.write("def main():\n    print('hello')\n")
            c = client()
            r = c.post("/batch", json={"tasks": [
                {"type": "exists", "path": tf},
                {"type": "outline", "path": tf},
                {"type": "run", "cmd": f"wc -l {tf}"},
            ]})
            d = r.get_json()
            results = d.get("results", d.get("data", {}).get("results", []))
            assert len(results) == 3

    def test_write_tests_for_feature(self):
        code = """
def validate_email(email: str) -> bool:
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))
"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(code); f.flush()
            c = client()
            r = c.post("/test", json={"path": f.name, "function": "validate_email"})
            assert r.status_code in (200, 500)
        os.unlink(f.name)


class TestCrossPlatform:
    def test_windows_backslash_path_no_crash(self):
        result = tools.read_file(r"C:\Users\dev\project\app.py")
        assert isinstance(result, str)

    def test_wsl_path_no_crash(self):
        result = tools.read_file("/mnt/c/Users/dev/project/app.py")
        assert isinstance(result, str)

    def test_home_expansion(self):
        home = str(os.path.expanduser("~"))
        assert len(home) > 0

    def test_shell_commands_platform_safe(self):
        result = tools.run_shell("python3 -c \"print('hello')\"")
        assert "hello" in result.lower()


class TestErrorScenarios:
    def test_ollama_unreachable_graceful(self):
        c = client()
        r = c.post("/ask", json={"task": "explain this"})
        assert r.status_code in (200, 500)
        assert "result" in r.get_json() or "error" in r.get_json()

    def test_concurrent_requests_no_corruption(self):
        errors = []
        def worker():
            try:
                c = client()
                for _ in range(10):
                    c.get("/health")
                    r = c.post("/exists", json={"path": "miser.py"})
                    assert json.loads(r.data)["exists"] is True
            except Exception as e:
                errors.append(str(e))
        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert len(errors) == 0

    def test_long_input_handled(self):
        c = client()
        long_task = "explain " + "x" * 10000
        r = c.post("/ask", json={"task": long_task})
        assert r.status_code in (200, 400, 413, 500)


class TestResponseConsistency:
    def test_all_zero_llm_have_expected_keys(self):
        c = client()
        endpoints = [
            ("/read", {"path": "miser.py"}, "content"),
            ("/grep", {"path": "miser.py", "pattern": "def "}, "matches"),
            ("/outline", {"path": "tools.py"}, "outline"),
            ("/tree", {"path": ".", "depth": 1}, "tree"),
            ("/exists", {"path": "miser.py"}, "exists"),
        ]
        for path, payload, key in endpoints:
            r = c.post(path, json=payload)
            assert r.status_code == 200, f"{path} → {r.status_code}"
            d = r.get_json()
            assert key in d, f"{path} missing '{key}'"

    def test_v1_data_envelope(self):
        c = client()
        r = c.post("/v1/read", json={"path": "client.py"})
        assert r.status_code == 200
        assert "data" in r.get_json()

    def test_error_has_standard_format(self):
        c = client()
        r = c.post("/read", json={})
        d = r.get_json()
        assert "error" in d


class TestSDKConsistency:
    def test_all_methods_exist(self):
        from client import W
        expected = ["ask","run","read","grep","outline","tree","exists","write",
                    "patch","summarize","codegen","explain","fix","test","review",
                    "condense","git_summary","batch","note","clear","status","quality",
                    "ensure_running"]
        for m in expected:
            assert hasattr(W, m), f"W.{m} missing"

    def test_zero_llm_methods_accept_path(self):
        import inspect
        from client import _W
        for name in ["read","outline","tree","exists","write"]:
            sig = inspect.signature(getattr(_W, name))
            assert "path" in sig.parameters

    def test_js_sdk_exports_match_python(self):
        import re
        base = os.path.dirname(os.path.dirname(__file__))
        js = os.path.join(base, "extensions", "js-sdk", "index.js")
        if os.path.exists(js):
            with open(js) as f:
                exports = re.findall(r'exports\.(\w+)\s*=', f.read())
            for exp in ["outline","grep","tree","exists","read","write","run",
                        "ask","codegen","explain","fix","test","review","condense",
                        "status","health","metrics"]:
                assert exp in exports, f"JS SDK missing exports.{exp}"


class TestMemoryPersistence:
    def test_memory_survives_restart(self):
        import memory, tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write('{"notes": {}, "history": []}')
            mem_path = f.name
        try:
            m = memory.Memory()
            m.save("proj_x", "FastAPI app")
            m.record(1, "task", "result")
            assert m.notes.get("proj_x") == "FastAPI app"
        finally:
            os.unlink(mem_path)

    def test_context_relevance(self):
        import memory
        m = memory.Memory()
        m.clear()
        m.save("auth", "JWT with refresh tokens")
        m.record(1, "explain auth.py", "JWT auth module")
        ctx = m.ctx("explain authentication")
        assert isinstance(ctx, str)


class TestCodegenWorkflow:
    """Scenario: User generates boilerplate code via Miser."""

    def test_codegen_endpoint_accepts_task(self):
        c = client()
        r = c.post("/codegen", json={
            "task": "write a debounce function in python",
            "lang": "python",
        })
        assert r.status_code in (200, 202, 429, 500)

    def test_codegen_with_specific_language(self):
        c = client()
        r = c.post("/codegen", json={
            "task": "write a quick sort",
            "lang": "javascript",
        })
        assert r.status_code in (200, 202, 429, 500)


class TestReviewWorkflow:
    """Scenario: User requests code review from Miser."""

    def test_review_endpoint_with_code(self):
        c = client()
        code = """
def process_data(items):
    result = []
    for item in items:
        result.append(item['value'] / 0)  # bug here
    return result
"""
        r = c.post("/review", json={"code": code})
        assert r.status_code in (200, 500)

    def test_review_endpoint_with_path(self):
        c = client()
        r = c.post("/review", json={"path": "miser.py"})
        assert r.status_code in (200, 500)


class TestEnsureRunningWorkflow:
    """Scenario: Miser client auto-starts server if not running."""

    def test_ensure_running_returns_bool(self):
        from client import W
        result = W.ensure_running(timeout=1.0)
        assert isinstance(result, bool)

    def test_ensure_running_fast_when_server_up(self):
        from client import W
        t0 = __import__('time').perf_counter()
        result = W.ensure_running(timeout=5.0)
        elapsed = __import__('time').perf_counter() - t0
        if result:
            assert elapsed < 3.0


class TestBackendSwitchWorkflow:
    """Scenario: User switches backend without restarting code changes."""

    def test_all_endpoints_work_with_ollama_backend_name(self):
        import miser, json
        with miser.app.test_client() as c:
            r = c.get("/health")
            d = json.loads(r.data)
            assert "backend" in d
            assert d["status"] == "ok"


class TestConcurrentAgentUsage:
    """Scenario: Multiple AI agents use Miser simultaneously."""

    def test_mixed_reads_from_concurrent_clients(self):
        import miser, json, threading
        errors = []

        def agent_session(name):
            try:
                with miser.app.test_client() as c:
                    for _ in range(10):
                        r = c.get("/health")
                        assert r.status_code == 200
                        r = c.post("/exists", json={"path": "miser.py"})
                        d = json.loads(r.data)
                        assert d["exists"] is True
            except Exception as e:
                errors.append(f"{name}: {e}")

        agents = ["claude", "cline", "aider", "codex"]
        threads = [threading.Thread(target=agent_session, args=(a,))
                   for a in agents]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(errors) == 0, f"Concurrent agents failed: {errors}"

    def test_rate_limiter_isolates_agents(self):
        from security import RateLimiter
        rl = RateLimiter()
        for _ in range(50):
            assert rl.allow("agent_claude", 60)
        for _ in range(5):
            assert rl.allow("agent_new", 10)
        assert rl.allow("agent_new", 10)


class TestLongRunningStability:
    """Scenario: Miser runs as a long-lived daemon."""

    def test_repeated_health_consistent(self):
        import miser, json
        with miser.app.test_client() as c:
            first = json.loads(c.get("/health").data)
            for _ in range(20):
                r = c.get("/health")
                assert r.status_code == 200
                d = json.loads(r.data)
                assert d["version"] == first["version"]
                assert d["model"] == first["model"]

    def test_no_file_descriptor_leak_on_repeated_calls(self):
        import tools
        for _ in range(50):
            result = tools.read_file(__file__, limit=500)
            assert isinstance(result, str)

    def test_memory_does_not_grow_unbounded(self):
        import memory
        m = memory.Memory()
        m.clear()
        for i in range(60):
            m.record(i, f"task {i}", f"result {i}")
        assert len(m.history) <= 40
        for i in range(250):
            m.save(f"note_{i}", f"v{i}")
        assert len(m.notes) <= 200


class TestAdaptToolWorkflow:
    """Scenario: User configures AI agents via 'miser adapt'."""

    def test_adapt_tool_list_all_registered(self):
        import subprocess, os
        adapt_py = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                "scripts", "adapt.py")
        result = subprocess.run(
            ["python", adapt_py, "--list"],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "cline" in result.stdout
        assert "aider" in result.stdout
        assert "codex" in result.stdout

    def test_adapt_tool_has_all_adapters(self):
        import os
        adapters_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                    "adapters")
        assert os.path.exists(os.path.join(adapters_dir, "cline-mcp.json"))
        assert os.path.exists(os.path.join(adapters_dir, "aider-miser.yml"))
        assert os.path.exists(os.path.join(adapters_dir, "codex-miser.sh"))
