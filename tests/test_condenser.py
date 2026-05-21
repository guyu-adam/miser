import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from condenser import distill, condensation_ratio, TEMPLATES


class TestTemplates:
    def test_all_templates_exist(self):
        assert "code_file" in TEMPLATES
        assert "error_log" in TEMPLATES
        assert "git_diff" in TEMPLATES
        assert "documentation" in TEMPLATES

    def test_each_template_is_string(self):
        for k, v in TEMPLATES.items():
            assert isinstance(v, str)
            assert len(v) > 50


class TestCondensationRatio:
    def test_basic_ratio(self):
        r = condensation_ratio("a" * 1000, "b" * 100)
        assert r["reduction_pct"] == 90
        assert r["tokens_saved"] == 225

    def test_zero_original(self):
        r = condensation_ratio("", "hello")
        assert r["original_chars"] == 0

    def test_long_text(self):
        r = condensation_ratio("x" * 8000, "y" * 200)
        assert r["reduction_pct"] >= 90

    def test_all_keys_present(self):
        r = condensation_ratio("hello world", "hi")
        for k in ("original_chars", "condensed_chars", "original_tokens_est",
                  "condensed_tokens_est", "tokens_saved", "reduction_pct"):
            assert k in r


class TestDistillShortText:
    def test_short_text_returns_original(self):
        """Text <200 chars should not go through LLM distillation."""
        result = distill("short text" * 5, "code_file")
        assert "short text" in result

    def test_empty_content(self):
        result = distill("", "code_file")
        assert result == ""


class TestDistillFallback:
    def test_category_fallback(self):
        """Unknown category should fall back to code_file template."""
        result = distill("some content " * 30, "unknown_category")
        assert isinstance(result, str)
