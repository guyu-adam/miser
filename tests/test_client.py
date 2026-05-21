import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from client import _check_llm, _flag, _extract_flags, _HALLUCINATION_PHRASES


class TestFlagFunction:
    def test_flag_prefix(self):
        result = _flag("some result", "TEST_FLAG")
        assert result.startswith("[MISER:TEST_FLAG]")

    def test_flag_preserves_content(self):
        result = _flag("hello world", "FLAG")
        assert "hello world" in result


class TestExtractFlags:
    def test_no_flag(self):
        assert _extract_flags("plain text") == []

    def test_single_flag(self):
        result = _extract_flags("[MISER:SYNTAX_ERROR:10]\ncode here")
        assert "SYNTAX_ERROR:10" in result

    def test_multiple_flags(self):
        result = _extract_flags("[MISER:A]\n[MISER:B]\ntext")
        assert len(result) >= 2

    def test_max_five_flags(self):
        result = _extract_flags("[MISER:1][MISER:2][MISER:3][MISER:4][MISER:5][MISER:6]")
        assert len(result) <= 5


class TestHallucinationDetection:
    def test_ai_refusal_flagged(self):
        result = _check_llm("I don't have access to that file", "explain")
        assert result.startswith("[MISER:")

    def test_as_an_ai_flagged(self):
        result = _check_llm("As an AI, I cannot do that", "ask")
        assert result.startswith("[MISER:")

    def test_normal_response_passes(self):
        result = _check_llm("This module defines the authentication middleware", "explain")
        assert not result.startswith("[MISER:")

    def test_all_hallucination_phrases_defined(self):
        assert len(_HALLUCINATION_PHRASES) >= 8


class TestTooShortDetection:
    def test_short_explain_flagged(self):
        result = _check_llm("ok", "explain")
        assert result.startswith("[MISER:TOO_SHORT]")

    def test_short_review_flagged(self):
        result = _check_llm("fine.", "review")
        assert result.startswith("[MISER:TOO_SHORT]")

    def test_short_ask_not_flagged(self):
        """ask endpoint shouldn't flag short answers."""
        result = _check_llm("4", "ask")
        assert not result.startswith("[MISER:")

    def test_long_enough_passes(self):
        result = _check_llm("This is a detailed explanation that is definitely long enough", "explain")
        assert not result.startswith("[MISER:TOO_SHORT]")


class TestSyntaxCheck:
    def test_valid_python_codegen(self):
        result = _check_llm("def hello():\n    return 'world'", "codegen")
        assert not result.startswith("[MISER:")

    def test_invalid_syntax_flagged(self):
        # Must be long enough to pass TOO_SHORT check
        result = _check_llm("def broken(:\n    this is invalid python syntax for sure", "codegen")
        assert "[MISER:SYNTAX_ERROR" in result

    def test_fenced_code_extraction(self):
        result = _check_llm("```python\ndef foo(): return 1\n```", "codegen")
        assert not result.startswith("[MISER:")


class TestContextMismatch:
    def test_relevant_explain_passes(self):
        ctx = "authentication middleware jwt token validation"
        result = _check_llm("This is the authentication middleware that validates JWT tokens", "explain", context=ctx)
        assert not result.startswith("[MISER:")

    def test_irrelevant_explain_flagged(self):
        ctx = "authentication middleware jwt token validation database sql"
        result = _check_llm("hello world foo bar baz qux " * 3, "explain", context=ctx)
        assert "[MISER:CONTEXT_MISMATCH]" in result


class TestEmptyResult:
    def test_none_result(self):
        assert _check_llm(None, "explain") is None

    def test_empty_string(self):
        result = _check_llm("", "explain")
        assert result == ""


class TestVerifyDisabled:
    def test_verify_flag_exists(self):
        import client
        w = client.W
        assert hasattr(w, 'verify')
        assert w.verify is True
