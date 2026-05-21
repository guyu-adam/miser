"""Accuracy tests — verify miser output against known ground truth."""
import sys, os, tempfile, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tools


class TestSafeEvalAccuracy:
    def test_add(self):       assert tools._safe_eval("42+1") == "43"
    def test_subtract(self):  assert tools._safe_eval("100-37") == "63"
    def test_multiply(self):  assert tools._safe_eval("7*9") == "63"
    def test_divide(self):    assert tools._safe_eval("10/4") == "2.5"
    def test_power(self):     assert tools._safe_eval("2^10") == "1024"
    def test_complex(self):   assert tools._safe_eval("(2+3)*(4+5)") == "45"
    def test_decimal(self):   assert "0.3" in tools._safe_eval("0.1+0.2")
    def test_large(self):     assert "1000000000" in tools._safe_eval("999999999+1")
    def test_negative(self):  assert tools._safe_eval("-100+50") == "-50"


class TestOutlineAccuracy:
    def _write_py(self, code):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
        f.write(code); f.close()
        return f.name

    def test_counts_functions(self):
        p = self._write_py("def a(): pass\ndef b(): pass\ndef c(): pass\n")
        result = tools.outline_file(p)
        assert result.count("def ") == 3
        os.unlink(p)

    def test_counts_classes(self):
        p = self._write_py("class Foo:\n    def m(self): pass\nclass Bar: pass\n")
        result = tools.outline_file(p)
        assert "class Foo" in result
        assert "class Bar" in result
        os.unlink(p)

    def test_line_numbers_correct(self):
        p = self._write_py("\n\ndef target_fn():\n    pass\n")
        result = tools.outline_file(p)
        assert "[L3]" in result
        os.unlink(p)

    def test_docstring_extraction(self):
        p = self._write_py('def foo():\n    """This does stuff"""\n    pass\n')
        result = tools.outline_file(p)
        assert "This does stuff" in result
        os.unlink(p)

    def test_indent_level(self):
        p = self._write_py("class A:\n    def inner():\n        pass\n")
        result = tools.outline_file(p)
        assert "  def inner" in result  # 4 spaces = 1 indent level
        os.unlink(p)


class TestGrepAccuracy:
    def _write(self, content):
        f = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False)
        f.write(content); f.close()
        return f.name

    def test_finds_all_occurrences(self):
        p = self._write("alpha\nbeta\nalpha\n")
        result = tools.grep_file(p, "alpha")
        assert result.count("alpha") >= 2
        os.unlink(p)

    def test_context_lines_count(self):
        p = self._write("line1\nline2\nMATCH\nline3\nline4\n")
        result = tools.grep_file(p, "MATCH", context=1)
        assert "line2" in result
        assert "line3" in result
        os.unlink(p)

    def test_no_false_positives(self):
        p = self._write("hello\nworld\n")
        result = tools.grep_file(p, "ZZZ_NOT_HERE")
        assert "No matches" in result
        os.unlink(p)

    def test_regex_metacharacters(self):
        p = self._write("func(x, y)\nfunc(a, b)\n")
        result = tools.grep_file(p, r"func\(.*\)")
        assert result.count("func") == 2
        os.unlink(p)


class TestReadWriteAccuracy:
    def test_roundtrip_preserves_content(self):
        p = "/tmp/_miser_acc_test.txt"
        original = "hello world\nline 2\nline 3"
        tools.write_to_file(p, original)
        content = tools.read_file(p)
        assert original in content
        os.unlink(p)

    def test_patch_correctness(self):
        p = "/tmp/_miser_patch_test.txt"
        tools.write_to_file(p, "abcdefg")
        tools.patch_file(p, "abc", "xyz")
        content = tools.read_file(p)
        assert content.startswith("xyz")
        os.unlink(p)


class TestExtractPathAccuracy:
    def test_tilde_expansion(self):
        r = tools.extract_path("read ~/project/main.py please", "/tmp")
        assert "~/" in r or "/" in r

    def test_absolute_path(self):
        r = tools.extract_path("analyze /etc/hosts file", "/tmp")
        assert r.startswith("/")

    def test_path_with_dots(self):
        r = tools.extract_path("read ./src/app.py", "/tmp")
        assert r != "/tmp"  # should extract actual path


class TestTokenCounterAccuracy:
    def test_counter_increments(self):
        start = tools.get_tokens_saved()
        tools.count_saved(4000)  # ~1000 tokens
        after = tools.get_tokens_saved()
        assert after >= start + 1000
