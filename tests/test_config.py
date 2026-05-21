"""Tests for config.py — configuration resolution."""
import os
from config import from_env, parse_cli, DEFAULTS


class TestFromEnv:
    def test_defaults_used_when_no_env(self):
        cfg = from_env()
        assert cfg["port"] == 7860
        assert cfg["model"] == "qwen3.5:4b"
        assert cfg["log_format"] == "text"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("MISER_PORT", "9090")
        monkeypatch.setenv("MISER_MODEL", "mistral:7b")
        monkeypatch.setenv("MISER_LOG_FORMAT", "json")
        cfg = from_env()
        assert cfg["port"] == 9090
        assert cfg["model"] == "mistral:7b"
        assert cfg["log_format"] == "json"


class TestParseCLI:
    def test_version_flag(self):
        cli = parse_cli(["--version"])
        assert cli.version is True

    def test_wizard_flag(self):
        cli = parse_cli(["--wizard"])
        assert cli.wizard is True

    def test_port_override(self):
        cli = parse_cli(["--port", "8080"])
        assert cli.port == 8080

    def test_model_override(self):
        cli = parse_cli(["--model", "llama3.1:8b"])
        assert cli.model == "llama3.1:8b"

    def test_default_port(self):
        cli = parse_cli([])
        assert cli.port == 7860

    def test_multiple_args(self):
        cli = parse_cli(["--port", "9000", "--log-format", "json", "--auth-token", "sec"])
        assert cli.port == 9000
        assert cli.log_format == "json"
        assert cli.auth_token == "sec"


class TestDefaults:
    def test_all_keys_present(self):
        expected = {"port", "model", "auth_token", "log_format", "embed_model",
                    "max_queue", "queue_timeout", "rate_llm", "rate_zero", "max_body_mb"}
        assert set(DEFAULTS.keys()) >= expected

    def test_port_default(self):
        assert DEFAULTS["port"] == 7860

    def test_rate_limits_reasonable(self):
        assert DEFAULTS["rate_llm"] == 30
        assert DEFAULTS["rate_zero"] == 200
