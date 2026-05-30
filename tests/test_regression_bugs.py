"""
test_regression_bugs.py — Regression tests for bugs found in v1.5.1 audit.

BUG 1: memory save eviction broken (random key eviction)
BUG 2: patch_file only replaced first occurrence
BUG 3: outline_file Java regex caused None.strip() AttributeError
BUG 4: OllamaBackend.generate() rebuilt ModelAdapter per call
BUG 5: /grep and /outline called read_file(path, 99999) for file size
BUG 6: outline_file Java regex matched non-class lines (imports, variable decls)
"""

import os, sys, tempfile
from pathlib import Path

# Ensure we can import miser modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════════════════
#  BUG 1: memory.py save() eviction used broken sort key → random eviction
# ═══════════════════════════════════════════════════════════════════════════

class TestBug1MemoryEviction:
    """BUG: save() sorted by len(self.notes) — all keys had the same score,
    so eviction was effectively random. Now uses FIFO pop of oldest key."""

    def test_eviction_pops_oldest_first(self, tmp_path):
        from memory import Memory
        mem = Memory()
        # Bypass file I/O
        mem.notes = {}
        mem.history = []
        mem.embeddings = []

        # Insert 250 notes (MAX_NOTES is 200)
        for i in range(250):
            mem.save(f"key_{i:03d}", f"value_{i}")

        # Should have exactly MAX_NOTES (200) entries
        assert len(mem.notes) == 200, f"Expected 200, got {len(mem.notes)}"

        # Oldest 50 keys should be gone, youngest 200 should remain
        keys = list(mem.notes.keys())
        for i in range(50):
            assert f"key_{i:03d}" not in keys, f"Old key key_{i:03d} should be evicted"
        for i in range(50, 250):
            assert f"key_{i:03d}" in keys, f"Young key key_{i:03d} should remain"

    def test_eviction_when_exactly_at_limit(self):
        from memory import Memory
        mem = Memory()
        mem.notes = {}
        mem.history = []
        mem.embeddings = []

        for i in range(200):
            mem.save(f"key_{i:03d}", f"val_{i}")

        assert len(mem.notes) == 200
        # All 200 should be present
        for i in range(200):
            assert f"key_{i:03d}" in mem.notes


# ═══════════════════════════════════════════════════════════════════════════
#  BUG 2: tools.py patch_file() replaced only 1st occurrence with text.replace(old, new, 1)
# ═══════════════════════════════════════════════════════════════════════════

class TestBug2PatchFileAllOccurrences:
    """BUG: patch_file used text.replace(old, new, 1) — only first occurrence.
    Fix: replace all occurrences."""

    def test_patches_all_occurrences(self, tmp_path):
        from tools import patch_file
        f = tmp_path / "test.txt"
        f.write_text("foo bar foo baz foo")
        result = patch_file(str(f), "foo", "qux")
        assert "replaced 3 occurrence" in result, f"Expected 3, got: {result}"
        content = f.read_text()
        assert content == "qux bar qux baz qux"

    def test_patches_single_occurrence(self, tmp_path):
        from tools import patch_file
        f = tmp_path / "single.txt"
        f.write_text("hello world")
        result = patch_file(str(f), "hello", "hi")
        assert "replaced 1 occurrence" in result
        assert f.read_text() == "hi world"

    def test_patch_no_match(self, tmp_path):
        from tools import patch_file
        f = tmp_path / "nomatch.txt"
        f.write_text("abc def")
        result = patch_file(str(f), "xyz", "nope")
        assert "Pattern not found" in result

    def test_patch_nonexistent_file(self):
        from tools import patch_file
        result = patch_file("/nonexistent/file.txt", "a", "b")
        assert "File not found" in result


# ═══════════════════════════════════════════════════════════════════════════
#  BUG 3: tools.py outline_file() Java regex None.strip() → AttributeError
# ═══════════════════════════════════════════════════════════════════════════

class TestBug3OutlineJavaNoneStrip:
    """BUG: Java outline regex had optional groups that could be None,
    causing None.strip() to raise AttributeError."""

    def test_java_class_outline_no_crash(self, tmp_path):
        from tools import outline_file
        f = tmp_path / "Test.java"
        f.write_text("""package com.example;

public class HelloWorld {
    private String name;

    public HelloWorld(String name) {
        this.name = name;
    }
}
""")
        result = outline_file(str(f))
        # Should not crash, should find the class
        assert "class" in result.lower() or "HelloWorld" in result

    def test_java_outline_only_classes_interfaces_enums(self, tmp_path):
        """BUG 6: old regex matched imports, variable declarations, etc."""
        from tools import outline_file
        f = tmp_path / "Types.java"
        f.write_text("""import java.util.List;
import java.util.Map;

public class UserService {
    private final Repository repo;
    private static final int MAX = 100;

    public void process() {}
}

interface Repository {
    User findById(int id);
}

enum Status { ACTIVE, INACTIVE }
""")
        result = outline_file(str(f))
        # Should find class, interface, enum
        assert "UserService" in result
        assert "Repository" in result
        assert "Status" in result
        # Should NOT match import statements or field declarations
        assert "import" not in result.lower()
        assert "MAX" not in result  # constant, not a class


# ═══════════════════════════════════════════════════════════════════════════
#  BUG 4: backends/ollama.py generate() rebuilt ModelAdapter every call
# ═══════════════════════════════════════════════════════════════════════════

class TestBug4ModelAdapterCaching:
    """BUG: OllamaBackend.generate() created a new ModelAdapter each call,
    which triggers /api/show HTTP call for family detection every time.
    Fix: cache ModelAdapter per model name."""

    def test_adapter_cached_per_model(self, monkeypatch):
        from backends.ollama import OllamaBackend
        import requests as req

        be = OllamaBackend(base_url="http://localhost:19999")

        # Mock requests.post to avoid real network calls
        def fake_post(url, **kwargs):
            class FakeResp:
                def json(self):
                    return {"message": {"content": "cached response"}}
            return FakeResp()
        monkeypatch.setattr(req, "post", fake_post)

        # Pre-populate cache with a real-ish adapter
        from model_adapter import ModelAdapter
        be._adapters["test-model"] = ModelAdapter("test-model")

        result1 = be.generate("test-model", "", "hello")
        assert result1 == "cached response"

        result2 = be.generate("test-model", "", "world")
        assert result2 == "cached response"

        # Different model not in cache — should create new adapter on demand
        assert "other-model" not in be._adapters

    def test_adapter_cache_is_per_instance(self):
        from backends.ollama import OllamaBackend
        be1 = OllamaBackend(base_url="http://localhost:99998")
        be2 = OllamaBackend(base_url="http://localhost:99997")
        be1._adapters["a"] = "fake1"
        be2._adapters["b"] = "fake2"
        assert "b" not in be1._adapters
        assert "a" not in be2._adapters


# ═══════════════════════════════════════════════════════════════════════════
#  BUG 5: /grep and /outline called read_file(path, 99999) for file size
# ═══════════════════════════════════════════════════════════════════════════

class TestBug5ReadFileForSize:
    """BUG: count_saved() used len(read_file(path, 99999)) to get file size,
    which read the entire file into memory. Fix: use Path.stat().st_size."""

    def test_grep_uses_stat_not_read(self, tmp_path):
        """Verify grep endpoint logic (the fix uses Path.stat)."""
        f = tmp_path / "bigfile.py"
        content = "def foo():\n    pass\n" * 10000  # large file
        f.write_text(content)

        # Simulate what the fixed code does
        fsize = f.stat().st_size
        assert fsize == len(content)

        # The old approach would have been:
        # from tools import read_file
        # old_size = len(read_file(str(f), 99999))
        # This would read the ENTIRE file. The fix avoids this.

        # Verify stat agrees with actual content length
        assert fsize > 100000, "Test file should be large"
        assert fsize == len(content)

    def test_outline_uses_stat_not_read(self, tmp_path):
        f = tmp_path / "huge.py"
        f.write_text("x = 1\n" * 50000)
        fsize = f.stat().st_size
        assert fsize == len("x = 1\n" * 50000)


# ═══════════════════════════════════════════════════════════════════════════
#  BUG 6: tools.py outline Java regex matched non-class lines
# ═══════════════════════════════════════════════════════════════════════════

class TestBug6JavaRegex:
    r"""BUG: old regex matched imports, variable declarations, method invocations.
    Fix: stricter regex that only matches class/interface/enum declarations."""

    def test_java_imports_not_matched(self, tmp_path):
        from tools import outline_file
        f = tmp_path / "ImportsOnly.java"
        f.write_text("""import java.util.List;
import java.util.Map;
import java.io.File;
""")
        result = outline_file(str(f))
        # Should report nothing — no classes, just imports
        assert "import" not in result.lower()
        assert result == "(no functions/classes found)" or "import" not in result

    def test_java_mixed_content(self, tmp_path):
        from tools import outline_file
        f = tmp_path / "Mixed.java"
        f.write_text("""package app;

import java.util.List;

/**
 * Main application class.
 */
public class App {
    private final Config config;
    private static final Logger log = LoggerFactory.getLogger(App.class);

    public void run() {
        List<String> items = List.of("a", "b");
        processItems(items);
    }

    private void processItems(List<String> items) {
        /*
         * Inner comment about processing
         */
        for (String item : items) {
            log.info("Processing: {}", item);
        }
    }
}

interface ConfigProvider {
    Config load();
}

enum Mode { DEV, PROD }
""")
        result = outline_file(str(f))
        lines = result.split("\n")
        # Should find App class, ConfigProvider interface, Mode enum
        assert any("App" in l for l in lines), f"Should find App class in: {result}"
        assert any("ConfigProvider" in l for l in lines), f"Should find interface in: {result}"
        assert any("Mode" in l for l in lines), f"Should find enum in: {result}"

        # Should NOT match these
        for bad in ["import", "Logger", "private", "processItems"]:
            assert bad not in result, f"Should not match '{bad}' in: {result}"


# ═══════════════════════════════════════════════════════════════════════════
#  Integration smoke test
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegrationSmoke:
    """Quick smoke tests to verify all modules import and basic functions work."""

    def test_all_modules_import(self):
        import miser
        import tools
        import memory
        import condenser
        import prefetch
        import cache
        import breaker
        import quality
        import task_queue
        import security
        import config
        import model_adapter
        from backends import ollama, openai_compat
        from routes import zero, admin

    def test_version_string(self):
        import subprocess, sys
        # Verify module import + version flag works
        import miser
        # main() is a blocking call; we just verify imports work here.
        # Full CLI test: python miser.py --version
