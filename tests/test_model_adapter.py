import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from model_adapter import (
    detect_family, has_thinking, use_raw_generate,
    build_prompt, clean_response, ModelAdapter, RECOMMENDED_MODELS,
)


class TestDetectFamily:
    def test_qwen3_from_qwen35(self):
        assert detect_family("qwen3.5:4b") == "qwen3"

    def test_qwen3_from_qwen3(self):
        assert detect_family("qwen3:8b") == "qwen3"

    def test_qwen2(self):
        assert detect_family("qwen2.5:7b") == "qwen2"
        assert detect_family("qwen2:7b") == "qwen2"

    def test_llama3(self):
        assert detect_family("llama3.1:8b") == "llama3"
        assert detect_family("llama3:8b") == "llama3"

    def test_llama2(self):
        assert detect_family("llama2:7b") == "llama2"

    def test_mistral(self):
        assert detect_family("mistral:7b") == "mistral"
        assert detect_family("mixtral:8x7b") == "mistral"

    def test_phi3(self):
        assert detect_family("phi3:mini") == "phi3"
        assert detect_family("phi-3:latest") == "phi3"

    def test_phi4(self):
        assert detect_family("phi4:latest") == "phi4"

    def test_gemma(self):
        assert detect_family("gemma:7b") == "gemma"
        assert detect_family("gemma3:4b") == "gemma"

    def test_deepseek_r1(self):
        assert detect_family("deepseek-r1:7b") == "deepseek-r1"

    def test_deepseek_coder(self):
        assert detect_family("deepseek-coder:6.7b") == "deepseek"

    def test_codellama(self):
        assert detect_family("codellama:7b") == "llama3"

    def test_unknown_model_returns_default(self):
        fam = detect_family("unknown-model-xyz")
        assert fam in ("default", "qwen3", "qwen2", "llama3", "llama2",
                       "mistral", "phi3", "phi4", "gemma", "deepseek", "deepseek-r1")


class TestThinkingDetection:
    def test_qwen3_has_thinking(self):
        assert has_thinking("qwen3")

    def test_deepseek_r1_has_thinking(self):
        assert has_thinking("deepseek-r1")

    def test_llama3_no_thinking(self):
        assert not has_thinking("llama3")

    def test_phi3_no_thinking(self):
        assert not has_thinking("phi3")


class TestRawGenerate:
    def test_qwen_uses_raw(self):
        assert use_raw_generate("qwen3")
        assert use_raw_generate("qwen2")

    def test_default_uses_chat(self):
        assert not use_raw_generate("default")


class TestPromptBuilders:
    def test_qwen3_prompt(self):
        p = build_prompt("qwen3", "System prompt", "User message")
        assert "<|im_start|>system" in p
        assert "System prompt" in p
        assert "User message" in p
        assert "<think>" in p  # qwen3-specific

    def test_qwen2_prompt_no_think(self):
        p = build_prompt("qwen2", "System", "User")
        assert "User" in p
        assert "<think>" not in p

    def test_llama3_prompt(self):
        p = build_prompt("llama3", "System", "User")
        assert "<|begin_of_text|>" in p
        assert "System" in p

    def test_llama2_prompt(self):
        p = build_prompt("llama2", "System", "User")
        assert "[INST]" in p
        assert "User" in p

    def test_mistral_prompt(self):
        p = build_prompt("mistral", "System", "User")
        assert "[INST]" in p

    def test_phi3_prompt(self):
        p = build_prompt("phi3", "System", "User")
        assert "<|user|>" in p

    def test_gemma_prompt(self):
        p = build_prompt("gemma", "System", "User")
        assert "<start_of_turn>" in p

    def test_deepseek_prompt(self):
        p = build_prompt("deepseek-r1", "System", "User")
        assert "User" in p

    def test_default_prompt(self):
        p = build_prompt("default", "System", "User")
        assert "User" in p

    def test_empty_system_qwen3(self):
        p = build_prompt("qwen3", "", "User")
        assert "User" in p
        assert "<|im_start|>user" in p

    def test_empty_system_llama2(self):
        p = build_prompt("llama2", "", "User")
        assert "[INST]" in p


class TestCleanResponse:
    def test_strip_think_block_qwen3(self):
        raw = "<think>blah blah</think>\nFinal answer."
        cleaned = clean_response(raw, "qwen3")
        assert "Final answer" in cleaned
        assert "blah blah" not in cleaned

    def test_strip_leaking_think(self):
        raw = "still thinking</think>\nActual answer"
        cleaned = clean_response(raw, "qwen3")
        assert "Actual" in cleaned

    def test_strip_code_fences(self):
        raw = "```python\nprint('hi')\n```"
        cleaned = clean_response(raw, "llama3")
        assert "```" not in cleaned
        assert "print('hi')" in cleaned

    def test_strip_eot(self):
        raw = "Good answer<|eot_id|>"
        cleaned = clean_response(raw, "llama3")
        assert "<|eot_id|>" not in cleaned

    def test_strip_im_end(self):
        raw = "Answer<|im_end|>"
        cleaned = clean_response(raw, "qwen2")
        assert "<|im_end|>" not in cleaned

    def test_code_mode_extracts_function(self):
        raw = "Here's the code:\n\ndef foo():\n    return 42\n\nThat's it."
        cleaned = clean_response(raw, "llama3", mode="code")
        assert "def foo" in cleaned

    def test_bullet_mode(self):
        raw = "- First point\n- Second point\n- Third point\nExtra text"
        cleaned = clean_response(raw, "llama3", mode="bullets")
        assert "First point" in cleaned

    def test_long_response_paras(self):
        raw = "The problem is...\n\nWe can fix it by...\n\nHowever, note that..."
        cleaned = clean_response(raw, "llama3", mode="text")
        assert len(cleaned) > 0

    def test_empty_input(self):
        assert clean_response("", "llama3") == ""


class TestModelAdapterClass:
    def test_adapter_creation(self):
        a = ModelAdapter("qwen3.5:4b")
        assert a.model == "qwen3.5:4b"
        assert a.family == "qwen3"

    def test_adapter_url(self):
        a = ModelAdapter("qwen3.5:4b")
        assert "/api/generate" in a.url

    def test_adapter_info(self):
        a = ModelAdapter("mistral:7b")
        info = a.info()
        assert info["model"] == "mistral:7b"
        assert info["family"] == "mistral"

    def test_generate_payload(self):
        a = ModelAdapter("qwen3.5:4b")
        payload = a.generate_payload("System", "User", max_tokens=300)
        assert "prompt" in payload or "messages" in payload
        assert payload["stream"] is False

    def test_extract_text(self):
        a = ModelAdapter("qwen3.5:4b")
        text = a.extract_text({"response": "Hello world"})
        assert text == "Hello world"

    def test_extract_text_from_chat(self):
        # Use a model that goes through chat API (not raw generate)
        a = ModelAdapter("command-r:latest")
        text = a.extract_text({"message": {"content": "Hi there"}})
        assert text == "Hi there"


class TestRecommendedModels:
    def test_all_categories_present(self):
        # Categories updated for 2026 models
        keys = {"4b_speed_qwen35", "8b_quality_llama4", "7b_quality_mistral",
                "code_qwen3_coder", "code_deepseek_v3", "phi4_windows", "gemma3_google"}
        assert set(RECOMMENDED_MODELS.keys()) >= keys

    def test_models_are_strings(self):
        for k, v in RECOMMENDED_MODELS.items():
            assert isinstance(v, str)
            assert len(v) > 0
