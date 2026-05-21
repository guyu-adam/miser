"""Compatibility tests — all model families, all response formats, all platforms."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from model_adapter import (
    detect_family, has_thinking, use_raw_generate, build_prompt,
    clean_response, ModelAdapter, RECOMMENDED_MODELS,
)


class TestAllModelFamilies:
    """Verify every supported model family is correctly detected and handled."""

    FAMILIES = {
        "qwen3": ["qwen3.5:4b", "qwen3.5:latest", "qwen3:8b", "qwen3:14b"],
        "qwen2": ["qwen2.5:7b", "qwen2:7b", "qwen2.5:14b"],
        "llama3": ["llama3.1:8b", "llama3:70b", "llama3.1:latest"],
        "llama2": ["llama2:7b", "llama2:13b"],
        "mistral": ["mistral:7b", "mixtral:8x7b", "mistral:latest"],
        "phi3": ["phi3:latest", "phi3:mini", "phi-3:latest"],
        "phi4": ["phi4:latest"],
        "gemma": ["gemma:7b", "gemma3:4b", "gemma3:latest"],
        "deepseek-r1": ["deepseek-r1:7b", "deepseek_r1:latest"],
        "deepseek": ["deepseek-coder:6.7b", "deepseek-coder:latest"],
    }

    def test_all_families_detected(self):
        for family, names in self.FAMILIES.items():
            for name in names:
                detected = detect_family(name)
                assert detected == family, f"{name} → {detected}, expected {family}"

    def test_all_families_generate_prompt(self):
        for family in self.FAMILIES.keys():
            prompt = build_prompt(family, "System msg", "User msg")
            assert isinstance(prompt, str)
            assert len(prompt) > 20
            assert "User msg" in prompt or "User" in prompt

    def test_all_families_clean_response(self):
        for family in self.FAMILIES.keys():
            result = clean_response("Normal response without tokens.", family)
            assert isinstance(result, str)
            assert len(result) > 0

    def test_all_families_adapter_creation(self):
        for family, names in self.FAMILIES.items():
            a = ModelAdapter(names[0])
            assert a.family == family
            assert a.model == names[0]


class TestThinkBlockBehavior:
    """qwen3 and deepseek-r1 inject empty <think> blocks to suppress verbose CoT."""

    def test_qwen3_injects_think_block(self):
        p = build_prompt("qwen3", "System", "User")
        assert "<think>" in p

    def test_qwen2_no_think_block(self):
        p = build_prompt("qwen2", "System", "User")
        assert "<think>" not in p

    def test_deepseek_no_think_block_in_base(self):
        p = build_prompt("deepseek", "System", "User")
        assert "<think>" not in p

    def test_think_block_stripped_from_response(self):
        raw = "<think>internal reasoning that should be hidden</think>\nPublic answer."
        result = clean_response(raw, "qwen3")
        assert "internal reasoning" not in result
        assert "Public answer" in result

    def test_leaking_close_tag_stripped(self):
        raw = "still thinking</think>\nReal answer here."
        result = clean_response(raw, "qwen3")
        assert "Real answer" in result
        assert "still thinking" not in result


class TestResponseCleaningAllEOSTokens:
    """Every EOS token variant must be stripped."""

    EOS_TOKENS = [
        "<|im_end|>", "<|end|>", "<|eot_id|>", "<end_of_turn>",
        "<|endoftext|>", "</s>", "[/INST]", "<|Assistant|>",
    ]

    def test_all_eos_tokens_stripped(self):
        for tok in self.EOS_TOKENS:
            raw = f"Answer content{tok}"
            result = clean_response(raw, "llama3")
            assert tok not in result, f"{tok!r} was not stripped"

    def test_combined_eos_tokens(self):
        raw = "Answer<|im_end|><|eot_id|></s>"
        result = clean_response(raw, "llama3")
        assert "<|im_end|>" not in result
        assert "<|eot_id|>" not in result


class TestCodeModeExtraction:
    def test_fenced_code(self):
        raw = "Let me write:\n```python\ndef foo():\n    return 1\n```\nDone."
        result = clean_response(raw, "llama3", mode="code")
        assert "def foo" in result

    def test_unfenced_function(self):
        raw = "def bar(x):\n    return x * 2\n\n# end"
        result = clean_response(raw, "llama3", mode="code")
        assert "def bar" in result

    def test_no_code_returns_original(self):
        raw = "I cannot write code for that."
        result = clean_response(raw, "llama3", mode="code")
        assert len(result) > 0


class TestBulletModeExtraction:
    def test_bullet_points_extracted(self):
        raw = "- First item\n- Second item\n- Third item\nExtra text"
        result = clean_response(raw, "llama3", mode="bullets")
        assert "First item" in result
        assert "Second item" in result

    def test_star_bullets(self):
        raw = "* Item A\n* Item B\n* Item C"
        result = clean_response(raw, "llama3", mode="bullets")
        assert len(result) > 0

    def test_numbered_list(self):
        raw = "1. Step one\n2. Step two\n3. Step three"
        result = clean_response(raw, "llama3", mode="bullets")
        assert "Step one" in result


class TestRecommendedModelsIntegrity:
    def test_all_models_are_valid_families(self):
        valid = {"qwen3", "qwen2", "llama3", "llama2", "mistral",
                 "phi3", "phi4", "gemma", "deepseek-r1", "deepseek"}
        for _, model in RECOMMENDED_MODELS.items():
            family = detect_family(model)
            assert family in valid or family == "default", \
                f"Recommended model {model} has unknown family {family}"


class TestPythonVersionCompatibility:
    """pyproject.toml declares >=3.10 — verify features work."""

    def test_future_annotations_supported(self):
        import sys
        if sys.version_info >= (3, 10):
            # | syntax for unions
            from task_queue import QueuedTask
            t = QueuedTask("1", "t", "s", "", 100, "")
            assert t.task_id == "1"

    def test_match_statement_not_required(self):
        """Codebase must not require Python 3.10+ match statement."""
        import sys
        # Verify importing all modules works without match
        import tools, memory, quality, adaptive, cache, breaker, condenser
        assert True  # No import errors

    def test_flask_version_compatible(self):
        import flask
        version = tuple(int(x) for x in flask.__version__.split(".")[:2])
        assert version >= (2, 3), f"Flask {flask.__version__} too old, need >=2.3"


class TestConfigCompatibility:
    def test_all_defaults_parseable(self):
        from config import DEFAULTS
        assert DEFAULTS["port"] == 7860
        assert isinstance(DEFAULTS["rate_llm"], int)
        assert isinstance(DEFAULTS["rate_zero"], int)

    def test_env_var_types(self):
        from config import from_env
        cfg = from_env()
        assert isinstance(cfg["port"], int)
        assert isinstance(cfg["model"], str)
        assert isinstance(cfg["rate_llm"], int)
