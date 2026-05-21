"""
quality.py — Quality router for Miser.
Ensures token savings never compromise session quality.

Architecture:
  CRITICAL ops → Claude handles directly (NEVER offload to local LLM)
  STANDARD ops → Miser handles, with verification
  SAFE ops     → Miser handles, no verification needed

Claude Code calls miser, gets back result + quality_decision.
Claude always has final say — miser is a co-processor, not a replacement.
"""

# ── Operation criticality ─────────────────────────────────────────────────────

CRITICAL_OPS = {
    # Security — Claude must verify
    "auth", "login", "password", "token", "jwt", "oauth", "ssl", "tls",
    "encrypt", "decrypt", "hash", "salt", "csrf", "xss", "cors",
    # Data integrity
    "delete", "drop", "truncate", "migrate", "schema",
    # Production
    "deploy", "release", "publish", "rollback",
    # Money
    "payment", "billing", "invoice", "charge", "refund",
}

STANDARD_OPS = {
    # Code understanding
    "explain", "review", "summarize", "outline",
    # Code generation
    "codegen", "test", "fix", "refactor",
    # General
    "ask", "chat",
}

SAFE_OPS = {
    # Deterministic, zero-LLM
    "read", "grep", "tree", "exists", "run", "write", "patch",
    "status", "memory", "note", "clear",
}

# ── Quality decision engine ───────────────────────────────────────────────────

class QualityDecision:
    """Returned alongside every miser response to guide Claude's behavior."""

    def __init__(self, op_type: str, source: str, flags: list = None,
                 confidence: float = 1.0, suggestion: str = ""):
        self.op_type = op_type
        self.source = source         # "claude" | "miser-zero" | "miser-llm"
        self.flags = flags or []
        self.confidence = confidence # 0.0 – 1.0
        self.suggestion = suggestion # advice for Claude

    @property
    def needs_claude_review(self) -> bool:
        return self.confidence < 0.70 or len(self.flags) > 0

    @property
    def is_safe(self) -> bool:
        return self.source in ("claude", "miser-zero") and not self.flags

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "confidence": self.confidence,
            "flags": self.flags,
            "needs_review": self.needs_claude_review,
            "suggestion": self.suggestion,
        }


def classify_op(task: str, op_type: str = "") -> str:
    """Classify an operation's criticality level."""
    task_lower = (task or "").lower()
    op_lower = (op_type or "").lower()

    # Explicit op type takes priority
    if op_lower in SAFE_OPS:
        return "safe"
    if op_lower in CRITICAL_OPS:
        return "critical"

    # Text-based classification for freeform /ask tasks
    for kw in CRITICAL_OPS:
        if kw in task_lower:
            return "critical"

    for kw in STANDARD_OPS:
        if kw in task_lower:
            return "standard"

    if op_lower in STANDARD_OPS:
        return "standard"

    return "standard"  # default


def should_offload(task: str, op_type: str = "") -> tuple[bool, str]:
    """
    Returns (should_offload, reason).
    True  = safe to send to miser's local LLM.
    False = Claude should handle this himself.
    """
    level = classify_op(task, op_type)

    if level == "critical":
        return False, "CRITICAL_OP: security/data/production concern — Claude must verify"

    if level == "safe":
        return True, "SAFE_OP: deterministic, no LLM involved"

    return True, "STANDARD_OP: suitable for local co-processing"


def estimate_confidence(result: str, op_type: str, flags: list) -> float:
    """Estimate confidence score for a local LLM result."""
    if not result:
        return 0.0

    # Deterministic ops are always 1.0
    if op_type in SAFE_OPS:
        return 1.0

    conf = 0.95  # base confidence for local LLM

    # Penalties for quality flags
    penalty_map = {
        "HALLUCINATION_RISK": 0.40,
        "SYNTAX_ERROR": 0.50,
        "TOO_SHORT": 0.25,
        "CONTEXT_MISMATCH": 0.30,
    }

    for flag in flags:
        for key, penalty in penalty_map.items():
            if key in flag:
                conf -= penalty

    # Too short results are less reliable
    if len(result.strip()) < 50 and op_type in ("explain", "review", "fix"):
        conf -= 0.15

    # Very long results might be rambling
    if len(result.strip()) > 2000 and op_type in ("codegen", "test"):
        conf -= 0.05

    return max(0.0, min(1.0, conf))


def quality_report(result, task: str, op_type: str, source: str,
                    flags: list = None) -> dict:
    """Generate a full quality report for Claude to consume."""
    flags = flags or []
    confidence = estimate_confidence(result, op_type, flags)
    level = classify_op(task, op_type)
    needs_review = confidence < 0.70 or len(flags) > 0

    suggestions = []
    if needs_review and level == "critical":
        suggestions.append("Claude should independently verify this result")
    if "HALLUCINATION_RISK" in str(flags):
        suggestions.append("Local model may have refused or hallucinated — treat as HINT not FACT")
    if "SYNTAX_ERROR" in str(flags):
        suggestions.append("Generated code has syntax errors — do NOT execute without fixing")
    if confidence < 0.50:
        suggestions.append("LOW CONFIDENCE — strongly recommend Claude re-does this task")

    return {
        "quality": {
            "source": source,
            "criticality": level,
            "confidence": round(confidence, 2),
            "flags": flags,
            "needs_claude_review": needs_review,
            "suggestions": suggestions,
        }
    }
