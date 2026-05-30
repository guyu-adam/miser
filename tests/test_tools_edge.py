import sys, os, tempfile, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tools


class TestSafeEvalEdge:
    def test_division_by_zero(self):
        result = tools._safe_eval("1/0")
        assert "error" in result.lower()

    def test_very_large_numbers(self):
        result = tools._safe_eval("99999999999+1")
        assert "100000000000" in result

    def test_decimal_math(self):
        result = tools._safe_eval("0.1+0.2")
        assert "0.3" in result

    def test_negative_power(self):
        result = tools._safe_eval("2^-2")
        assert "0.25" in result

    def test_parens_nested(self):
        result = tools._safe_eval("((1+2)*(3+4))")
        assert "21" in result

    def test_unary_minus_precedence(self):
        result = tools._safe_eval("-2^2")
        assert "-4" in result or "-4.0" in result

    def test_empty_expression(self):
        r = tools._safe_eval("")
        assert "error" in r.lower()

    def test_only_spaces(self):
        r = tools._safe_eval("   ")
        assert "error" in r.lower()

    def test_float_division(self):
        result = tools._safe_eval("5/2")
        assert "2.5" in result

    def test_modulo_not_allowed(self):
        r = tools._safe_eval("10%3")
        assert "error" in r.lower() or "Unsupported" in r


class TestGrepEdge:
    def test_grep_with_unicode(self):
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8')
        tf.write("# 中文注释\nprint('hello')\n# 日本語\n")
        tf.close()
        result = tools.grep_file(tf.name, "中文")
        assert "中文" in result
        os.unlink(tf.name)

    def test_grep_context_lines(self):
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        tf.write("line1\nline2\ntarget\nline3\nline4\n")
        tf.close()
        result = tools.grep_file(tf.name, "target", context=1)
        assert "line2" in result
        assert "line3" in result
        os.unlink(tf.name)

    def test_grep_case_sensitive(self):
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        tf.write("Hello\nHELLO\n")
        tf.close()
        result = tools.grep_file(tf.name, "Hello", context=0, ignore_case=False)
        assert "Hello" in result
        assert "HELLO" not in result
        os.unlink(tf.name)

    def test_grep_empty_file(self):
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        tf.write("")
        tf.close()
        result = tools.grep_file(tf.name, "anything")
        assert "No matches" in result
        os.unlink(tf.name)


class TestOutlineEdge:
    def test_outline_empty_file(self):
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        tf.write("")
        tf.close()
        result = tools.outline_file(tf.name)
        assert "no functions" in result.lower()
        os.unlink(tf.name)

    def test_outline_async_def(self):
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        tf.write("async def fetch_data():\n    pass\n")
        tf.close()
        result = tools.outline_file(tf.name)
        assert "async def fetch_data" in result
        os.unlink(tf.name)

    def test_outline_go_file(self):
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.go', delete=False)
        tf.write("func main() {\n}\ntype Config struct {\n}\n")
        tf.close()
        result = tools.outline_file(tf.name)
        assert "main" in result or "func" in result
        os.unlink(tf.name)

    def test_outline_js_file(self):
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False)
        tf.write("function init() {}\nclass App {}\nconst x = 1;\n")
        tf.close()
        result = tools.outline_file(tf.name)
        assert "init" in result or "App" in result
        os.unlink(tf.name)


class TestTreeEdge:
    def test_tree_nonexistent(self):
        result = tools.tree_view("/nonexistent/zzz123")
        assert "not found" in result.lower()

    def test_tree_with_exclusion(self):
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.pyc', dir='/tmp', delete=False)
        tf.write("x=1")
        tf.close()
        result = tools.tree_view("/tmp", depth=1, exclude="__pycache__,node_modules,*.pyc")
        # Should not crash
        assert isinstance(result, str)
        os.unlink(tf.name)

    def test_tree_default_depth(self):
        result = tools.tree_view(".", depth=1)
        assert "client.py" in result or "miser.py" in result


class TestPatchEdge:
    def test_patch_single_occurrence(self):
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        tf.write("hello world")
        tf.close()
        result = tools.patch_file(tf.name, "world", "miser")
        assert "Patched" in result
        content = open(tf.name).read()
        assert "hello miser" in content
        os.unlink(tf.name)

    def test_patch_multiple_occurrences_replaces_one(self):
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        tf.write("aaa bbb aaa")
        tf.close()
        result = tools.patch_file(tf.name, "aaa", "xxx")
        assert "2 occurrence" in result  # v1.5.1: replace ALL occurrences
        os.unlink(tf.name)

    def test_patch_not_found(self):
        tf = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        tf.write("hello")
        tf.close()
        result = tools.patch_file(tf.name, "nonexistent", "x")
        assert "not found" in result.lower()
        os.unlink(tf.name)

    def test_patch_missing_file(self):
        result = tools.patch_file("/tmp/zzz_nonexistent.txt", "a", "b")
        assert "not found" in result.lower()


class TestWriteEdge:
    def test_write_creates_parent_dirs(self):
        p = "/tmp/_miser_test_deep/nested/dir/test.txt"
        result = tools.write_to_file(p, "hello")
        assert "Written" in result
        assert os.path.exists(p)
        os.unlink(p)
        os.removedirs("/tmp/_miser_test_deep/nested/dir")

    def test_write_overwrites(self):
        p = "/tmp/_miser_test_overwrite.txt"
        tools.write_to_file(p, "first")
        tools.write_to_file(p, "second")
        content = open(p).read()
        assert content == "second"
        os.unlink(p)


class TestRunShellEdge:
    def test_run_with_timeout(self):
        result = tools.run_shell("sleep 1", timeout=2)
        assert "BLOCKED" not in result

    def test_blocked_chmod(self):
        result = tools.run_shell("chmod 777 /tmp/test")
        assert "BLOCKED" in result

    def test_blocked_sudo(self):
        result = tools.run_shell("sudo ls")
        assert "BLOCKED" in result

    def test_blocked_dd(self):
        result = tools.run_shell("dd if=/dev/zero of=/tmp/x bs=1 count=1")
        assert "BLOCKED" in result

    def test_blocked_mkfs(self):
        result = tools.run_shell("mkfs.ext4 /dev/sda1")
        assert "BLOCKED" in result


class TestExtractPathEdge:
    def test_path_with_spaces_still_extracted(self):
        r = tools.extract_path("read ~/my projects/app.py", "/tmp")
        assert "~/" in r or "/" in r

    def test_path_with_hyphens(self):
        r = tools.extract_path("open /tmp/my-file_v2.py", "/tmp")
        assert "my-file" in r or "/tmp" in r

    def test_default_returned_when_no_path(self):
        r = tools.extract_path("hello world no path here", "/tmp/default")
        assert r == "/tmp/default"


class TestListDir:
    def test_list_current_dir(self):
        result = tools.list_dir(".")
        assert "client.py" in result or "miser.py" in result

    def test_list_nonexistent(self):
        result = tools.list_dir("/nonexistent/zzz")
        assert "not found" in result.lower()
