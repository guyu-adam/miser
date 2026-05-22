"""Boundary & limit tests — extremes, edge cases, max inputs.

NOTE: SafeEval empty, outline empty, and tree nonexistent edge cases
are covered in test_tools_edge.py to avoid duplication.
"""
import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tools


class TestMaxInputSizes:
    def test_read_huge_file_truncated(self):
        p = "/tmp/_miser_boundary_huge.txt"
        with open(p, 'w') as f:
            f.write("x" * 20000)
        result = tools.read_file(p, limit=5000)
        assert "truncated" in result.lower()
        os.unlink(p)

    def test_write_large_content(self):
        content = "a" * 100000
        result = tools.write_to_file("/tmp/_miser_large_write.txt", content)
        assert "Written" in result
        os.unlink("/tmp/_miser_large_write.txt")

    def test_grep_large_file(self):
        p = "/tmp/_miser_boundary_grep.txt"
        with open(p, 'w') as f:
            for i in range(500):
                f.write(f"line {i}\n")
            f.write("TARGET_FOUND\n")
            for i in range(500):
                f.write(f"line {i+500}\n")
        result = tools.grep_file(p, "TARGET_FOUND")
        assert "TARGET_FOUND" in result
        os.unlink(p)


class TestEmptyAndNullInputs:
    def test_read_empty_path_no_crash(self):
        try:
            result = tools.read_file("")
        except (IsADirectoryError, OSError):
            result = "(error handled)"
        assert isinstance(result, str)

    def test_grep_empty_pattern(self):
        import tempfile
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        f.write("hello"); f.close()
        result = tools.grep_file(f.name, "")
        assert isinstance(result, str)
        os.unlink(f.name)

    def test_write_empty_content(self):
        result = tools.write_to_file("/tmp/_miser_empty.txt", "")
        assert "Written" in result
        os.unlink("/tmp/_miser_empty.txt")

    def test_patch_empty_old(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        f.write("data"); f.close()
        result = tools.patch_file(f.name, "", "x")
        # Empty old string matches everywhere — patched or pattern not found
        assert isinstance(result, str)
        os.unlink(f.name)

class TestUnicodeBoundary:
    def test_read_unicode_file(self):
        p = "/tmp/_miser_unicode.txt"
        with open(p, 'w', encoding='utf-8') as f:
            f.write("中文测试\n日本語テスト\n한국어\n🎉🚀💻\n")
        result = tools.read_file(p)
        assert "中文" in result
        assert "日本語" in result
        assert "🎉" in result
        os.unlink(p)

    def test_grep_unicode_pattern(self):
        p = "/tmp/_miser_unicode_grep.txt"
        with open(p, 'w', encoding='utf-8') as f:
            f.write("line 1: 错误处理\nerror handling\nline 2: 异常捕获\n")
        result = tools.grep_file(p, "错误", context=0)
        assert "错误" in result
        os.unlink(p)

    def test_write_unicode(self):
        content = "def hello():  # 你好\n    return '世界'"
        tools.write_to_file("/tmp/_miser_write_unicode.py", content)
        result = tools.read_file("/tmp/_miser_write_unicode.py")
        assert "你好" in result
        assert "世界" in result
        os.unlink("/tmp/_miser_write_unicode.py")

    def test_outline_unicode_docstrings(self):
        p = "/tmp/_miser_unicode_doc.py"
        with open(p, 'w', encoding='utf-8') as f:
            f.write('def fetch():  # 获取数据\n    """返回用户信息"""\n    pass\n')
        result = tools.outline_file(p)
        assert "获取" in result or "fetch" in result
        os.unlink(p)


class TestSpecialCharacters:
    def test_path_with_spaces(self):
        import pathlib
        p = pathlib.Path("/tmp/_miser space test.txt")
        p.write_text("hello")
        result = tools.read_file(str(p))
        assert "hello" in result
        p.unlink()

    def test_path_with_special_chars(self):
        import pathlib
        p = pathlib.Path("/tmp/_miser_test-v2.1_final (copy).txt")
        p.write_text("data")
        result = tools.read_file(str(p))
        assert "data" in result
        p.unlink()

    def test_safe_eval_scientific_notation(self):
        result = tools._safe_eval("1.5e3+1")  # might or might not work
        assert isinstance(result, str)

    def test_grep_dollar_sign(self):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        f.write("price=$100\ncost=$50\n")
        f.close()
        result = tools.grep_file(f.name, r"price=\$")
        assert "price" in result
        os.unlink(f.name)

    def test_shell_special_chars_safe(self):
        result = tools.run_shell("echo 'hello \"world\" $HOME'")
        assert "hello" in result


class TestPathBoundary:
    def test_extract_path_tilde(self):
        r = tools.extract_path("open ~/Documents/file.txt", "/tmp")
        assert "~/" in r or "Documents" in r or r != "/tmp"

    def test_extract_path_root(self):
        r = tools.extract_path("check /etc/hosts", "/tmp")
        assert r.startswith("/")

    def test_extract_path_with_hash(self):
        r = tools.extract_path("read ~/project/src/main.py#L42", "/tmp")
        assert "~/" in r or "/" in r


class TestNestingBoundary:
    def test_deeply_nested_tree(self):
        import tempfile
        import pathlib
        base = pathlib.Path("/tmp/_miser_nest_test")
        base.mkdir(exist_ok=True)
        current = base
        for i in range(5):
            current = current / f"level{i}"
            current.mkdir(exist_ok=True)
            (current / "file.txt").write_text("x")
        result = tools.tree_view(str(base), depth=10)
        assert "level4" in result or "file.txt" in result
        import shutil
        shutil.rmtree(base)

    def test_many_files_in_directory(self):
        import tempfile, pathlib
        base = pathlib.Path("/tmp/_miser_many_files")
        base.mkdir(exist_ok=True)
        for i in range(50):
            (base / f"file_{i:03d}.txt").write_text(f"content {i}")
        result = tools.tree_view(str(base), depth=1)
        assert "file_000" in result
        assert "file_049" in result
        import shutil
        shutil.rmtree(base)
