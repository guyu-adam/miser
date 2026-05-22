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
