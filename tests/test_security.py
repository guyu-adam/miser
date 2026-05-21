"""Tests for security.py — rate limit, auth, CORS, error codes."""
from security import (
    RateLimiter, hash_token, verify_token, error_response,
    ALLOWED_ORIGINS, ERROR_CODES,
)


class TestRateLimiter:
    def test_allow_within_limit(self):
        rl = RateLimiter()
        for _ in range(5):
            assert rl.allow("test", 10)
        assert rl.remaining("test", 10) == 5

    def test_deny_over_limit(self):
        rl = RateLimiter()
        for _ in range(3):
            rl.allow("strict", 3)
        assert not rl.allow("strict", 3)

    def test_different_keys_independent(self):
        rl = RateLimiter()
        for _ in range(30):
            rl.allow("key_a", 30)
        assert rl.allow("key_b", 5)
        assert not rl.allow("key_a", 30)

    def test_remaining(self):
        rl = RateLimiter()
        assert rl.remaining("fresh", 10) == 10
        rl.allow("fresh", 10)
        assert rl.remaining("fresh", 10) == 9


class TestAuthHashing:
    def test_hash_produces_different_value(self):
        h = hash_token("my-secret-token")
        assert h != "my-secret-token"
        assert len(h) == 64  # SHA256

    def test_verify_correct_token(self):
        h = hash_token("correct")
        assert verify_token("correct", h)

    def test_verify_wrong_token(self):
        h = hash_token("correct")
        assert not verify_token("wrong", h)

    def test_empty_token_bypass(self):
        assert verify_token("", "")

    def test_no_auth_configured(self):
        assert verify_token("anything", "")


class TestCORS:
    def test_localhost_allowed(self):
        assert "http://localhost" in ALLOWED_ORIGINS
        assert "http://127.0.0.1" in ALLOWED_ORIGINS

    def test_non_localhost_rejected(self):
        assert "http://evil.com" not in ALLOWED_ORIGINS
        assert "https://localhost" not in ALLOWED_ORIGINS


class TestErrorResponse:
    def _get(self, *args, **kw):
        from flask import Response
        r = error_response(*args, **kw)
        assert isinstance(r, Response)
        import json
        return r.status_code, json.loads(r.data)

    def test_missing_param(self):
        status, data = self._get("E_MISSING_PARAM")
        assert status == 400
        assert data["error"]["code"] == "E_MISSING_PARAM"

    def test_not_found(self):
        status, _ = self._get("E_NOT_FOUND")
        assert status == 404

    def test_rate_limited(self):
        status, _ = self._get("E_RATE_LIMITED")
        assert status == 429

    def test_internal(self):
        status, _ = self._get("E_INTERNAL")
        assert status == 500

    def test_unknown_code_defaults_500(self):
        status, _ = self._get("E_UNKNOWN_XYZ")
        assert status == 500

    def test_custom_detail_and_status(self):
        status, data = self._get("E_AUTH_REQUIRED", detail="Please login", status=403)
        assert status == 403
        assert data["error"]["detail"] == "Please login"

    def test_all_error_codes_present(self):
        expected = {"E_MISSING_PARAM", "E_NOT_FOUND", "E_BUSY", "E_RATE_LIMITED",
                    "E_QUEUE_FULL", "E_AUTH_REQUIRED", "E_AUTH_INVALID",
                    "E_LARGE_BODY", "E_INTERNAL", "E_OLLAMA_DOWN"}
        assert set(ERROR_CODES.keys()) == expected
