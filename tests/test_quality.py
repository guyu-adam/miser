"""Tests for quality.py and adaptive.py — routing decisions."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from quality import classify_op, should_offload, estimate_confidence


class TestClassifyOp:
    def test_security_is_critical(self):
        assert classify_op("fix login bug with jwt token", "fix") == "critical"
        assert classify_op("add password hashing", "codegen") == "critical"

    def test_payment_is_critical(self):
        assert classify_op("generate payment module", "codegen") == "critical"
        assert classify_op("debug billing error", "fix") == "critical"

    def test_deploy_is_critical(self):
        assert classify_op("deploy to production", "ask") == "critical"
        assert classify_op("rollback the release", "ask") == "critical"

    def test_explain_is_standard(self):
        assert classify_op("explain this caching module", "explain") == "standard"

    def test_test_gen_is_standard(self):
        assert classify_op("write unit tests for utils", "test") == "standard"

    def test_read_is_safe(self):
        assert classify_op("read the config file", "read") == "safe"

    def test_run_is_safe(self):
        assert classify_op("git status", "run") == "safe"


class TestShouldOffload:
    def test_critical_not_offloaded(self):
        ok, reason = should_offload("add JWT auth to login", "codegen")
        assert not ok
        assert "CRITICAL" in reason

    def test_standard_is_offloaded(self):
        ok, reason = should_offload("explain the utils module", "explain")
        assert ok

    def test_safe_is_offloaded(self):
        ok, reason = should_offload("ls -la", "run")
        assert ok


class TestConfidenceEstimation:
    def test_safe_ops_full_confidence(self):
        conf = estimate_confidence("result", "read", [])
        assert conf == 1.0

    def test_hallucination_penalty(self):
        conf = estimate_confidence("some result", "explain", ["HALLUCINATION_RISK"])
        assert conf < 0.70

    def test_syntax_error_penalty(self):
        conf = estimate_confidence("code", "codegen", ["SYNTAX_ERROR:10"])
        assert conf < 0.60

    def test_empty_result_zero(self):
        conf = estimate_confidence("", "explain", [])
        assert conf == 0.0

    def test_clean_result_high_confidence(self):
        conf = estimate_confidence("This is a detailed and correct explanation of the module's architecture", "explain", [])
        assert conf > 0.80
