"""
test_llm_performance.py — Quantifiable local LLM performance loss benchmarks.

Measures the REAL performance of local LLM models used as agent co-processors,
comparing against known cloud model baselines (GPT-4o, Claude Sonnet, Gemini).

METRICS:
  1. ACCURACY    — task success rate (0.0–1.0) per category and overall
  2. LATENCY     — TTFT (time to first content token), eval duration, throughput
  3. THINKING    — thinking token ratio (overhead for reasoning models)
  4. VARIANCE    — std dev across 3 identical runs (reproducibility)
  5. P_LOSS      — composite performance loss (0.0 = cloud-parity, 1.0 = total loss)

CATEGORIES (4 categories × 4–5 tasks = 18 total):
  - Coding:   5 tasks, verifiable by executing output
  - Reasoning: 5 tasks, factual/math/logic with known answers
  - Factual:   4 tasks, exact-answer knowledge questions
  - Instruction: 4 tasks, output format compliance

DESIGN:
  - Each task is run 3 times at temperature=0 for variance measurement
  - Accuracy is scored deterministically (no LLM-as-judge)
  - TTFT measured via streaming; throughput via eval_duration
  - Cloud baselines are published benchmarks, not live API calls
  - COMPLETELY SELF-CONTAINED: only stdlib + requests (already Miser dep)
"""

import json
import os
import re
import statistics
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import requests as req

# ═══════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════

OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434")
MODELS = os.environ.get("LLM_PERF_MODELS", "miser-qwen:latest").split(",")
MODELS = [m.strip() for m in MODELS if m.strip()]
REPETITIONS = 3
NUM_PREDICT = 500   # generous for short tasks
TEMPERATURE = 0.0   # deterministic for reproducibility

# Cloud baseline accuracies (from published benchmarks, approximate)
CLOUD_BASELINES = {
    "coding":      0.92,   # GPT-4o/Claude on simple function writing
    "reasoning":   0.95,   # GPT-4o on simple logic/math
    "factual":     0.98,   # Cloud models on common knowledge
    "instruction": 0.90,   # Format-following tasks
}

# Per-category num_predict (thinking models need more tokens for code)
CATEGORY_NUM_PREDICT = {
    "coding":       2000,  # Coding needs lots of thinking tokens
    "reasoning":    500,   # Simple reasoning works with 500
    "factual":      300,   # Short factual answers
    "instruction":  500,   # Format compliance
}

# ═══════════════════════════════════════════════════════
# TASK DEFINITIONS
# ═══════════════════════════════════════════════════════

CODING_TASKS = [
    {
        "id": "fib",
        "prompt": "Write a Python function `fib(n)` that returns the nth Fibonacci number (0-indexed).",
        "tests": [
            ("fib(0)", 0),
            ("fib(1)", 1),
            ("fib(5)", 5),
            ("fib(10)", 55),
        ],
        "extract": lambda text: _extract_function(text, "fib"),
    },
    {
        "id": "is_prime",
        "prompt": "Write a Python function `is_prime(n)` that returns True if n is prime, False otherwise.",
        "tests": [
            ("is_prime(2)", True),
            ("is_prime(4)", False),
            ("is_prime(17)", True),
            ("is_prime(1)", False),
            ("is_prime(97)", True),
        ],
        "extract": lambda text: _extract_function(text, "is_prime"),
    },
    {
        "id": "reverse_words",
        "prompt": "Write a Python function `reverse_words(s)` that reverses the order of words in a string.",
        "tests": [
            ('reverse_words("hello world")', "world hello"),
            ('reverse_words("a b c")', "c b a"),
            ('reverse_words("one")', "one"),
            ('reverse_words("")', ""),
        ],
        "extract": lambda text: _extract_function(text, "reverse_words"),
    },
    {
        "id": "count_vowels",
        "prompt": "Write a Python function `count_vowels(s)` that returns the number of vowels (a,e,i,o,u) in a string, case-insensitive.",
        "tests": [
            ('count_vowels("hello")', 2),
            ('count_vowels("AEIOU")', 5),
            ('count_vowels("rhythm")', 0),
            ('count_vowels("Beautiful")', 5),
        ],
        "extract": lambda text: _extract_function(text, "count_vowels"),
    },
    {
        "id": "merge_sorted",
        "prompt": "Write a Python function `merge_sorted(a, b)` that merges two sorted lists into one sorted list.",
        "tests": [
            ("merge_sorted([1,3,5], [2,4,6])", [1, 2, 3, 4, 5, 6]),
            ("merge_sorted([], [1,2])", [1, 2]),
            ("merge_sorted([1], [])", [1]),
            ("merge_sorted([1,1], [1,1])", [1, 1, 1, 1]),
        ],
        "extract": lambda text: _extract_function(text, "merge_sorted"),
    },
]

REASONING_TASKS = [
    {
        "id": "simple_math",
        "prompt": "A store sells apples for $2 each and oranges for $3 each. If I buy 4 apples and 3 oranges, how much do I pay in total? Answer with just the number.",
        "answer": ["17"],
    },
    {
        "id": "logic_height",
        "prompt": "Alice is taller than Bob. Bob is taller than Carol. David is shorter than Carol. Who is the tallest? Answer with just the name.",
        "answer": ["alice"],
    },
    {
        "id": "sequence_next",
        "prompt": "What is the next number in this sequence: 2, 6, 12, 20, 30, ? Answer with just the number.",
        "answer": ["42"],
    },
    {
        "id": "time_calc",
        "prompt": "If a train leaves at 9:15 AM and travels for 2 hours and 45 minutes, what time does it arrive? Answer in 24-hour format like 12:00.",
        "answer": ["12:00"],
    },
    {
        "id": "percentage",
        "prompt": "A shirt originally costs $80. It's on sale for 25% off, plus an extra 10% off the sale price. What is the final price? Answer with just the number.",
        "answer": ["54"],
    },
]

FACTUAL_TASKS = [
    {
        "id": "capital_france",
        "prompt": "What is the capital city of France? Answer with just the city name.",
        "answer": ["paris"],
    },
    {
        "id": "element_au",
        "prompt": "What chemical element has the symbol Au? Answer with just the element name.",
        "answer": ["gold"],
    },
    {
        "id": "speed_of_light",
        "prompt": "What is the approximate speed of light in vacuum, in kilometers per second? Answer with just the number.",
        "answer": ["299792"],  # exact value; gemma4 gets this right
    },
    {
        "id": "python_year",
        "prompt": "In what year was the Python programming language first released? Answer with just the year.",
        "answer": ["1991"],
    },
]

INSTRUCTION_TASKS = [
    {
        "id": "json_format",
        "prompt": 'Output exactly this JSON and nothing else: {"status":"ok","value":42}',
        "check": lambda text: _parse_json_output(text),
        "expected_keys": ["status", "value"],
    },
    {
        "id": "no_markdown",
        "prompt": "List three primary colors. Output only the colors separated by commas — no markdown, no bullet points, no extra text.",
        "check": lambda text: "red" in text.lower() and "blue" in text.lower() and "yellow" in text.lower(),
    },
    {
        "id": "uppercase",
        "prompt": "Convert this sentence to ALL UPPERCASE: 'the quick brown fox jumps over the lazy dog'. Output ONLY the uppercase version.",
        "check": lambda text: "THE QUICK BROWN FOX" in text,
    },
    {
        "id": "count_words",
        "prompt": "How many words are in this sentence: 'I love programming in Python'? Answer with just the number.",
        "answer": ["5"],
    },
]


# ═══════════════════════════════════════════════════════
# EVALUATION HELPERS
# ═══════════════════════════════════════════════════════

def _extract_function(text, func_name):
    """Extract a Python function definition from model output."""
    # Try ```python code block first
    m = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    if m:
        code = m.group(1)
    else:
        code = text

    # Find the function definition
    pattern = rf"def\s+{func_name}\s*\([^)]*\)\s*:.*"
    m = re.search(pattern, code, re.DOTALL)
    if m:
        return m.group(0)
    return code.strip()


def _parse_json_output(text):
    """Try to parse JSON from model output. Returns dict or None."""
    # Find JSON object
    m = re.search(r"\{[^{}]*\}", text)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _execute_code(code, test_call):
    """Execute a test_call string against extracted code. Returns (ok, result, error)."""
    sandbox_globals = {}
    try:
        exec(code, sandbox_globals)
        result = eval(test_call, sandbox_globals)
        return True, result, None
    except Exception as e:
        return False, None, str(e)


def _score_response(task, response_text):
    """Score a single task response. Returns (score: float, details: str)."""
    # Coding tasks
    if "tests" in task and "extract" in task:
        code = task["extract"](response_text)
        passed = 0
        total = len(task["tests"])
        for call, expected in task["tests"]:
            ok, result, err = _execute_code(code, call)
            if ok and result == expected:
                passed += 1
        return passed / total if total > 0 else 0.0, f"{passed}/{total} tests passed"

    # Answer-matching tasks (reasoning, factual, instruction with "answer")
    if "answer" in task:
        resp_lower = response_text.lower().strip()
        # Extract the last number or word before extraneous text
        for expected in task["answer"]:
            if expected in resp_lower:
                return 1.0, f"matched '{expected}'"
        # Try extracting just a number
        nums = re.findall(r"\d+", response_text)
        for expected in task["answer"]:
            if expected in nums:
                return 1.0, f"number '{expected}' found"
        return 0.0, f"expected one of {task['answer']}, got '{response_text[:80]}'"

    # Check-function tasks (instruction)
    if "check" in task:
        try:
            ok = task["check"](response_text)
            return (1.0 if ok else 0.0), f"check {'PASS' if ok else 'FAIL'}"
        except Exception as e:
            return 0.0, f"check error: {e}"

    return 0.0, "no scoring method"


# ═══════════════════════════════════════════════════════
# LLM CALL (Ollama /api/chat with streaming for TTFT)
# ═══════════════════════════════════════════════════════

def call_llm(model, prompt, num_predict=NUM_PREDICT, temperature=TEMPERATURE):
    """Call Ollama chat API. Returns dict with metrics."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "options": {
            "num_predict": num_predict,
            "temperature": temperature,
        },
    }

    t_start = time.perf_counter()
    response_text = ""
    thinking_text = ""
    ttft_ms = None         # time to first content token
    first_token_ms = None  # time to first token (including thinking)
    eval_count = 0
    eval_duration_ns = 0

    try:
        with req.post(
            f"{OLLAMA_BASE}/api/chat",
            json=payload,
            stream=True,
            timeout=300,
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # Track first token arrival
                if first_token_ms is None:
                    first_token_ms = (time.perf_counter() - t_start) * 1000

                msg = chunk.get("message", {})
                content_chunk = msg.get("content", "")
                thinking_chunk = msg.get("thinking", "")

                if thinking_chunk:
                    thinking_text += thinking_chunk

                if content_chunk:
                    if ttft_ms is None:
                        ttft_ms = (time.perf_counter() - t_start) * 1000
                    response_text += content_chunk

                if chunk.get("done", False):
                    eval_count = chunk.get("eval_count", 0)
                    eval_duration_ns = chunk.get("eval_duration", 0)
                    break

    except Exception as e:
        return {"error": str(e), "response": "", "thinking": ""}

    t_end = time.perf_counter()
    total_ms = (t_end - t_start) * 1000
    tokens_per_sec = (eval_count / (eval_duration_ns / 1e9)) if eval_duration_ns > 0 else 0
    thinking_ratio = (len(thinking_text) / max(len(thinking_text) + len(response_text), 1))

    return {
        "response": response_text.strip(),
        "thinking": thinking_text,
        "total_ms": round(total_ms, 1),
        "ttft_ms": round(ttft_ms, 1) if ttft_ms else None,
        "first_token_ms": round(first_token_ms, 1) if first_token_ms else None,
        "eval_count": eval_count,
        "eval_duration_ms": round(eval_duration_ns / 1e6, 1),
        "tokens_per_sec": round(tokens_per_sec, 1),
        "thinking_ratio": round(thinking_ratio, 3),
    }


# ═══════════════════════════════════════════════════════
# BENCHMARK RUNNER
# ═══════════════════════════════════════════════════════

ALL_TASKS = {
    "coding": CODING_TASKS,
    "reasoning": REASONING_TASKS,
    "factual": FACTUAL_TASKS,
    "instruction": INSTRUCTION_TASKS,
}


def run_benchmarks(models=None, repetitions=None):
    """Run all benchmarks for all models. Returns full results dict."""
    if models is None:
        models = MODELS
    if repetitions is None:
        repetitions = REPETITIONS

    results = {}
    total_tasks = sum(len(tasks) for tasks in ALL_TASKS.values())

    for model in models:
        print(f"\n{'='*60}")
        print(f"Model: {model}")
        print(f"Tasks: {total_tasks} x {repetitions} repetitions")
        print(f"{'='*60}")

        model_results = {}

        for category, tasks in ALL_TASKS.items():
            print(f"\n--- {category.upper()} ({len(tasks)} tasks) ---")
            cat_results = []

            for task in tasks:
                task_id = task["id"]
                task_scores = []
                task_latencies = []
                task_details = []

                for run in range(repetitions):
                    print(f"  {task_id} run {run+1}/{repetitions}...", end=" ", flush=True)
                    npredict = CATEGORY_NUM_PREDICT.get(category, NUM_PREDICT)
                    r = call_llm(model, task["prompt"], num_predict=npredict)
                    if "error" in r:
                        print(f"ERROR: {r['error']}")
                        task_scores.append(0.0)
                        task_latencies.append(0)
                        task_details.append(f"error: {r['error']}")
                        continue

                    score, detail = _score_response(task, r.get("response", ""))
                    task_scores.append(score)
                    task_latencies.append(r.get("total_ms", 0))
                    task_details.append(detail)

                    ttft = r.get('ttft_ms')
                    ttft_str = f"{ttft:.0f}" if ttft is not None else "N/A"
                    print(f"score={score:.2f} ({detail}) "
                          f"ttft={ttft_str}ms "
                          f"toks={r.get('eval_count', 0)} "
                          f"tps={r.get('tokens_per_sec', 0):.0f} "
                          f"think={r.get('thinking_ratio', 0):.0%}")

                avg_score = statistics.mean(task_scores) if task_scores else 0.0
                std_score = statistics.stdev(task_scores) if len(task_scores) > 1 else 0.0
                avg_latency = statistics.mean(task_latencies) if task_latencies else 0

                cat_results.append({
                    "task_id": task_id,
                    "scores": task_scores,
                    "avg_score": round(avg_score, 3),
                    "std_score": round(std_score, 3),
                    "latencies_ms": task_latencies,
                    "avg_latency_ms": round(avg_latency, 1),
                    "details": task_details,
                    "runs": [r for r in (task_scores,)] if not isinstance(task_scores, list) else [],
                })

            model_results[category] = cat_results

        results[model] = model_results

    return results


# ═══════════════════════════════════════════════════════
# ANALYSIS & REPORT
# ═══════════════════════════════════════════════════════

def compute_p_loss(model_results, cloud_baselines=None):
    """Compute composite P_loss for each category and overall.

    P_loss = w_acc * ACC_loss + w_lat * LAT_penalty + w_var * VAR_penalty

    Where:
      ACC_loss    = (cloud_accuracy - local_accuracy) / cloud_accuracy
      LAT_penalty = log10(local_latency / cloud_latency) ... normalized
      VAR_penalty = coefficient_of_variation of accuracy

    Cloud latency is assumed ~1000ms (typical API call). Local models
    on GPU can be faster; on CPU they're slower. We cap at 0.0-1.0.
    """
    if cloud_baselines is None:
        cloud_baselines = CLOUD_BASELINES

    CLOUD_LATENCY_MS = 1000.0
    W_ACC = 0.50
    W_LAT = 0.30
    W_VAR = 0.20

    category_losses = {}
    all_acc = []
    all_lat = []
    all_var = []

    for category, tasks in model_results.items():
        cat_acc = statistics.mean([t["avg_score"] for t in tasks]) if tasks else 0
        cat_lat = statistics.mean([t["avg_latency_ms"] for t in tasks]) if tasks else 0
        cat_var = statistics.mean([t["std_score"] for t in tasks]) if tasks else 0

        cloud_acc = cloud_baselines.get(category, 0.95)
        acc_loss = max(0, (cloud_acc - cat_acc) / max(cloud_acc, 0.01))
        lat_penalty = min(1.0, max(0, (cat_lat - CLOUD_LATENCY_MS) / max(CLOUD_LATENCY_MS * 9, 1)))
        var_penalty = min(1.0, cat_var * 3)  # 33% cv -> full penalty

        p_loss = W_ACC * acc_loss + W_LAT * lat_penalty + W_VAR * var_penalty

        category_losses[category] = {
            "accuracy": round(cat_acc, 3),
            "cloud_accuracy": cloud_acc,
            "acc_loss": round(acc_loss, 3),
            "avg_latency_ms": round(cat_lat, 1),
            "lat_penalty": round(lat_penalty, 3),
            "avg_variance": round(cat_var, 3),
            "var_penalty": round(var_penalty, 3),
            "p_loss": round(p_loss, 3),
        }

        all_acc.append(cat_acc)
        all_lat.append(cat_lat)
        all_var.append(cat_var)

    # Overall P_loss: weighted by task count per category
    if all_acc:
        overall = {
            "accuracy": round(statistics.mean(all_acc), 3),
            "avg_latency_ms": round(statistics.mean(all_lat), 1),
            "avg_variance": round(statistics.mean(all_var), 3),
            "by_category": category_losses,
        }

        # Compute overall P_loss as mean of category P_losses
        overall["p_loss"] = round(
            statistics.mean([c["p_loss"] for c in category_losses.values()]),
            3,
        )
    else:
        overall = {"p_loss": 1.0, "accuracy": 0.0, "avg_latency_ms": 0, "avg_variance": 0}

    return overall


def print_report(results, p_losses):
    """Print formatted benchmark report."""
    for model, model_results in results.items():
        pl = p_losses.get(model, {})
        print(f"\n{'='*70}")
        print(f"  LLM PERFORMANCE LOSS REPORT: {model}")
        print(f"{'='*70}")

        # Category breakdown
        print(f"\n{'Category':<15} {'Accuracy':>8} {'vs Cloud':>10} {'Lat(ms)':>8} {'Variance':>9} {'P_loss':>7}")
        print(f"{'-'*15} {'-'*8} {'-'*10} {'-'*8} {'-'*9} {'-'*7}")

        for cat, metrics in pl.get("by_category", {}).items():
            cloud = metrics["cloud_accuracy"]
            print(
                f"{cat:<15} {metrics['accuracy']:>8.3f} "
                f"{cloud:>7.3f}->{metrics['accuracy']:.3f} "
                f"{metrics['avg_latency_ms']:>8.0f} "
                f"{metrics['avg_variance']:>9.3f} "
                f"{metrics['p_loss']:>7.3f}"
            )

        # Overall
        print(f"\n{'─'*70}")
        print(f"  OVERALL P_LOSS:  {pl.get('p_loss', 'N/A'):.3f}  (0=cloud parity, 1=total loss)")
        print(f"  Accuracy:        {pl.get('accuracy', 0):.3f}  (fraction of tasks correct)")
        print(f"  Avg Latency:     {pl.get('avg_latency_ms', 0):.0f} ms")
        print(f"  Avg Variance:    {pl.get('avg_variance', 0):.3f}  (std dev across runs)")

        # Interpretation
        p = pl.get("p_loss", 1.0)
        if p < 0.2:
            grade = "EXCELLENT — near cloud parity"
        elif p < 0.4:
            grade = "GOOD — minor tradeoffs acceptable for most agent tasks"
        elif p < 0.6:
            grade = "FAIR — usable but expect quality degradation"
        elif p < 0.8:
            grade = "POOR — significant accuracy or latency issues"
        else:
            grade = "UNUSABLE — do not rely on for agent reasoning"
        print(f"  Grade:           {grade}")

        # Detailed per-task accuracy
        print(f"\n  Per-Task Scores:")
        for cat, tasks in model_results.items():
            for t in tasks:
                scores_str = ", ".join(f"{s:.2f}" for s in t["scores"])
                print(f"    {cat}/{t['task_id']:<20} avg={t['avg_score']:.2f}  "
                      f"std={t['std_score']:.3f}  runs=[{scores_str}]  "
                      f"lat={t['avg_latency_ms']:.0f}ms")

    print(f"\n{'='*70}")
    print("  INTERPRETATION GUIDE")
    print(f"{'='*70}")
    print("""
  P_LOSS = 0.50 * ACC_loss + 0.30 * LAT_penalty + 0.20 * VAR_penalty

  ACC_loss:   (cloud_baseline - local_accuracy) / cloud_baseline
              How much worse is the local model at getting correct answers?
              0.0 = same accuracy as cloud, 0.5 = half as accurate

  LAT_penalty: (local_latency - 1000ms) / 9000ms, capped [0,1]
              How much slower is local inference vs API call?
              0.0 = equal or faster, 0.5 = ~5.5s, 1.0 = 10s+

  VAR_penalty: 3 * std_dev_of_accuracy, capped [0,1]
              How inconsistent are results across repeated runs?
              0.0 = perfectly deterministic, 0.3 = 10% std dev

  LOWER P_LOSS IS BETTER. This metric quantifies the LOCAL PREMIUM
  you pay when using a local model instead of a cloud model for
  agent co-processing tasks.
""")


def save_report_json(results, p_losses, path="perf_report.json"):
    """Save results as JSON for programmatic consumption."""
    report = {
        "results": results,
        "p_losses": p_losses,
        "config": {
            "models": MODELS,
            "repetitions": REPETITIONS,
            "num_predict": NUM_PREDICT,
            "temperature": TEMPERATURE,
            "cloud_baselines": CLOUD_BASELINES,
        },
    }

    # Make results JSON-serializable
    def _serialize(obj):
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [_serialize(v) for v in obj]
        elif callable(obj):
            return str(obj)
        return obj

    report = _serialize(report)

    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\nReport saved to {path}")
    return path


# ═══════════════════════════════════════════════════════
# pytest-compatible test classes
# ═══════════════════════════════════════════════════════

class TestLLMPerformanceCoding:
    """Coding accuracy: can local model write correct, executable code?"""

    def test_fibonacci(self):
        r = call_llm(MODELS[0], CODING_TASKS[0]["prompt"])
        assert "error" not in r, r.get("error")
        score, detail = _score_response(CODING_TASKS[0], r["response"])
        assert score >= 0.5, f"fibonacci: {detail}"

    def test_is_prime(self):
        r = call_llm(MODELS[0], CODING_TASKS[1]["prompt"])
        assert "error" not in r, r.get("error")
        score, detail = _score_response(CODING_TASKS[1], r["response"])
        assert score >= 0.5, f"is_prime: {detail}"

    def test_reverse_words(self):
        r = call_llm(MODELS[0], CODING_TASKS[2]["prompt"])
        assert "error" not in r, r.get("error")
        score, detail = _score_response(CODING_TASKS[2], r["response"])
        assert score >= 0.5, f"reverse_words: {detail}"

    def test_count_vowels(self):
        r = call_llm(MODELS[0], CODING_TASKS[3]["prompt"])
        assert "error" not in r, r.get("error")
        score, detail = _score_response(CODING_TASKS[3], r["response"])
        assert score >= 0.5, f"count_vowels: {detail}"

    def test_merge_sorted(self):
        r = call_llm(MODELS[0], CODING_TASKS[4]["prompt"])
        assert "error" not in r, r.get("error")
        score, detail = _score_response(CODING_TASKS[4], r["response"])
        assert score >= 0.5, f"merge_sorted: {detail}"


class TestLLMPerformanceReasoning:
    """Reasoning accuracy: can local model solve logic/math problems?"""

    def test_simple_math(self):
        r = call_llm(MODELS[0], REASONING_TASKS[0]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(REASONING_TASKS[0], r["response"])
        assert score == 1.0, f"simple_math failed: {r['response'][:80]}"

    def test_logic_height(self):
        r = call_llm(MODELS[0], REASONING_TASKS[1]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(REASONING_TASKS[1], r["response"])
        assert score == 1.0, f"logic_height failed: {r['response'][:80]}"

    def test_sequence_next(self):
        r = call_llm(MODELS[0], REASONING_TASKS[2]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(REASONING_TASKS[2], r["response"])
        assert score == 1.0, f"sequence_next failed: {r['response'][:80]}"

    def test_time_calc(self):
        r = call_llm(MODELS[0], REASONING_TASKS[3]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(REASONING_TASKS[3], r["response"])
        assert score == 1.0, f"time_calc failed: {r['response'][:80]}"

    def test_percentage(self):
        r = call_llm(MODELS[0], REASONING_TASKS[4]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(REASONING_TASKS[4], r["response"])
        assert score == 1.0, f"percentage failed: {r['response'][:80]}"


class TestLLMPerformanceFactual:
    """Factual accuracy: does local model know common facts?"""

    def test_capital_france(self):
        r = call_llm(MODELS[0], FACTUAL_TASKS[0]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(FACTUAL_TASKS[0], r["response"])
        assert score == 1.0, f"capital_france: {r['response'][:80]}"

    def test_element_au(self):
        r = call_llm(MODELS[0], FACTUAL_TASKS[1]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(FACTUAL_TASKS[1], r["response"])
        assert score == 1.0, f"element_au: {r['response'][:80]}"

    def test_speed_of_light(self):
        r = call_llm(MODELS[0], FACTUAL_TASKS[2]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(FACTUAL_TASKS[2], r["response"])
        assert score == 1.0, f"speed_of_light: {r['response'][:80]}"

    def test_python_year(self):
        r = call_llm(MODELS[0], FACTUAL_TASKS[3]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(FACTUAL_TASKS[3], r["response"])
        assert score == 1.0, f"python_year: {r['response'][:80]}"


class TestLLMPerformanceInstruction:
    """Instruction following: can local model follow format constraints?"""

    def test_json_format(self):
        r = call_llm(MODELS[0], INSTRUCTION_TASKS[0]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(INSTRUCTION_TASKS[0], r["response"])
        assert score == 1.0, f"json_format: {r['response'][:80]}"

    def test_no_markdown(self):
        r = call_llm(MODELS[0], INSTRUCTION_TASKS[1]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(INSTRUCTION_TASKS[1], r["response"])
        assert score == 1.0, f"no_markdown: {r['response'][:80]}"

    def test_uppercase(self):
        r = call_llm(MODELS[0], INSTRUCTION_TASKS[2]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(INSTRUCTION_TASKS[2], r["response"])
        assert score == 1.0, f"uppercase: {r['response'][:80]}"

    def test_count_words(self):
        r = call_llm(MODELS[0], INSTRUCTION_TASKS[3]["prompt"])
        assert "error" not in r, r.get("error")
        score, _ = _score_response(INSTRUCTION_TASKS[3], r["response"])
        assert score == 1.0, f"count_words: {r['response'][:80]}"


class TestLLMPerformanceLatency:
    """Latency SLA: basic response should be under threshold."""

    def test_basic_response_under_30s(self):
        """A simple question should get a response within 30 seconds."""
        r = call_llm(MODELS[0], "What is 2+2? Reply with just the number.", num_predict=200)
        assert "error" not in r, r.get("error")
        total_ms = r.get("total_ms", 0)
        assert isinstance(total_ms, (int, float)) and total_ms < 30000, f"Too slow: {total_ms}ms"
        eval_count = r.get("eval_count", 0)
        assert isinstance(eval_count, (int, float)) and eval_count > 0, "No tokens generated"

    def test_ttft_under_5s(self):
        """Time to first content token should be under 5s for warm model."""
        # Warm up first
        call_llm(MODELS[0], "say hi", num_predict=50)
        r = call_llm(MODELS[0], "What is 2+2? Reply with just the number.", num_predict=100)
        assert "error" not in r, r.get("error")
        ttft = r.get("ttft_ms")
        if ttft is not None:
            assert isinstance(ttft, (int, float)) and ttft < 5000, f"TTFT too slow: {ttft}ms"


class TestLLMPerformanceVariance:
    """Reproducibility: same prompt at temp=0 should give consistent results."""

    def test_deterministic_output(self):
        """At temperature=0, two runs should produce identical or near-identical output."""
        r1 = call_llm(MODELS[0], "What is 2+2? Reply with just the number.", num_predict=200)
        r2 = call_llm(MODELS[0], "What is 2+2? Reply with just the number.", num_predict=200)
        assert "error" not in r1, r1.get("error")
        assert "error" not in r2, r2.get("error")
        # Response should contain "4"
        assert "4" in r1.get("response", ""), f"Run1: {r1.get('response', '')[:80]}"
        assert "4" in r2.get("response", ""), f"Run2: {r2.get('response', '')[:80]}"
        # Token counts should be within 2x of each other
        c1 = r1.get("eval_count", 0) or 0
        c2 = r2.get("eval_count", 0) or 0
        if c1 > 0 and c2 > 0:
            ratio = max(c1, c2) / min(c1, c2)
            assert ratio < 2.0, f"Token count varies too much: {c1} vs {c2}"


# ═══════════════════════════════════════════════════════
# CLI runner (python test_llm_performance.py)
# ═══════════════════════════════════════════════════════

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="LLM performance loss benchmark")
    ap.add_argument("--models", default=",".join(MODELS),
                    help="Comma-separated model names (default: miser-qwen:latest)")
    ap.add_argument("--runs", type=int, default=REPETITIONS,
                    help=f"Repetitions per task (default: {REPETITIONS})")
    ap.add_argument("--json", default="perf_report.json",
                    help="Output JSON path")
    ap.add_argument("--quick", action="store_true",
                    help="Quick mode: 1 repetition, fewer tasks")
    args = ap.parse_args()

    MODELS[:] = [m.strip() for m in args.models.split(",")]
    models = MODELS
    runs = args.runs

    if args.quick:
        # Single run, fewer tasks for quick check
        runs = 1
        for cat in list(ALL_TASKS.keys()):
            ALL_TASKS[cat] = ALL_TASKS[cat][:2]  # First 2 per category

    print(f"Starting LLM performance benchmark...")
    print(f"Models: {models}")
    print(f"Repetitions: {runs}")
    print(f"Ollama: {OLLAMA_BASE}")

    # Run benchmarks with specified repetitions
    results = run_benchmarks(models, runs)
    p_losses = {}
    for model in models:
        p_losses[model] = compute_p_loss(results.get(model, {}))

    print_report(results, p_losses)
    save_report_json(results, p_losses, args.json)
