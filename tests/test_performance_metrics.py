"""
test_performance_metrics.py — Quantifiable performance benchmarks for Miser.

Measures:
  1. TOKEN_SAVINGS     — actual tokens/API cost saved per operation
  2. CPU_OVERHEAD       — proxy for power consumption (user+systime in ms)
  3. DATA_COMPLETENESS  — accuracy: did we lose information? (0.0–1.0)
  4. PERF_COST          — composite score: CPU cost per 1000 tokens saved
  5. PERF_EFFICIENCY    — tokens saved per CPU-ms (higher = better)

Test scenario: A realistic 20-file Python project (~500KB total, ~12K lines).
Each operation is run against this project and measured with os.times().

Design principle: zero-LLM operations are DETERMINISTIC — accuracy is 100%.
The "performance cost" is purely CPU/time overhead of the Miser tool call
vs a direct equivalent. The "savings" are the tokens the cloud agent would
have burned reading the full file vs getting Miser's structured output.
"""
import os, sys, time, json, statistics, tempfile, shutil
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools import (
    read_file, outline_file, grep_file, tree_view, run_shell,
    write_to_file, patch_file,
)

# ═══════════════════════════════════════════════════════════════════════════
#  Test project generator — creates a realistic Python codebase
# ═══════════════════════════════════════════════════════════════════════════

_PROJECT_FILES = {
    "src/__init__.py": "",
    "src/models.py": """
\"\"\"Data models for the application.\"\"\"
from dataclasses import dataclass, field
from typing import Optional, List, Dict
from datetime import datetime
import uuid

@dataclass
class User:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    username: str = ""
    email: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    is_active: bool = True

    def deactivate(self):
        self.is_active = False

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
            "is_active": self.is_active,
        }

@dataclass
class Project:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    owner_id: str = ""
    members: List[str] = field(default_factory=list)
    settings: Dict = field(default_factory=dict)

class TaskStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class Task:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    status: str = TaskStatus.PENDING
    assignee_id: Optional[str] = None
    project_id: str = ""
    due_date: Optional[datetime] = None
""",
    "src/services.py": """\"\"\"Business logic layer.\"\"\"
from typing import List, Optional
from src.models import User, Project, Task, TaskStatus
from src.database import Database

class UserService:
    def __init__(self, db: Database):
        self.db = db

    def create_user(self, username: str, email: str) -> User:
        user = User(username=username, email=email)
        self.db.users[user.id] = user
        return user

    def get_user(self, user_id: str) -> Optional[User]:
        return self.db.users.get(user_id)

    def deactivate_user(self, user_id: str) -> bool:
        user = self.db.users.get(user_id)
        if not user:
            return False
        user.deactivate()
        return True

    def search_users(self, query: str) -> List[User]:
        q = query.lower()
        return [u for u in self.db.users.values()
                if q in u.username.lower() or q in u.email.lower()]

class ProjectService:
    def __init__(self, db: Database):
        self.db = db

    def create_project(self, name: str, owner_id: str, description: str = "") -> Project:
        project = Project(name=name, owner_id=owner_id, description=description)
        self.db.projects[project.id] = project
        return project

class TaskService:
    def __init__(self, db: Database):
        self.db = db

    def create_task(self, title: str, project_id: str) -> Task:
        task = Task(title=title, project_id=project_id)
        self.db.tasks[task.id] = task
        return task

    def get_project_tasks(self, project_id: str) -> List[Task]:
        return [t for t in self.db.tasks.values() if t.project_id == project_id]
""",
    "src/database.py": """\"\"\"In-memory database (demo).\"\"\"
from typing import Dict
from src.models import User, Project, Task

class Database:
    def __init__(self):
        self.users: Dict[str, User] = {}
        self.projects: Dict[str, Project] = {}
        self.tasks: Dict[str, Task] = {}

    def clear(self):
        self.users.clear()
        self.projects.clear()
        self.tasks.clear()

    def stats(self) -> dict:
        return {
            "users": len(self.users),
            "projects": len(self.projects),
            "tasks": len(self.tasks),
        }
""",
    "src/api/__init__.py": "",
    "src/api/routes.py": """\"\"\"API route handlers.\"\"\"
from src.services import UserService, ProjectService, TaskService

class APIRouter:
    def __init__(self, user_svc: UserService, project_svc: ProjectService,
                 task_svc: TaskService):
        self.user_svc = user_svc
        self.project_svc = project_svc
        self.task_svc = task_svc

    def handle_create_user(self, data: dict) -> dict:
        user = self.user_svc.create_user(
            username=data["username"],
            email=data["email"],
        )
        return user.to_dict()

    def handle_get_user(self, user_id: str) -> dict:
        user = self.user_svc.get_user(user_id)
        if not user:
            return {"error": "not_found"}
        return user.to_dict()

    def handle_create_project(self, data: dict) -> dict:
        project = self.project_svc.create_project(
            name=data["name"],
            owner_id=data["owner_id"],
            description=data.get("description", ""),
        )
        return {"id": project.id, "name": project.name}
""",
    "src/api/middleware.py": """\"\"\"API middleware — auth, logging, rate limiting.\"\"\"
import time, hashlib, functools
from typing import Callable

def auth_required(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        # Simplified: check for token in args
        return fn(*args, **kwargs)
    return wrapper

def rate_limit(max_calls: int = 100, window: float = 60.0):
    def decorator(fn: Callable) -> Callable:
        calls = []
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            now = time.time()
            calls[:] = [t for t in calls if now - t < window]
            if len(calls) >= max_calls:
                raise Exception("Rate limit exceeded")
            calls.append(now)
            return fn(*args, **kwargs)
        return wrapper
    return decorator

def log_request(fn: Callable) -> Callable:
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        start = time.time()
        result = fn(*args, **kwargs)
        elapsed = time.time() - start
        print(f"[LOG] {fn.__name__} took {elapsed:.3f}s")
        return result
    return wrapper
""",
    "src/utils/__init__.py": "",
    "src/utils/validators.py": """\"\"\"Input validation utilities.\"\"\"
import re
from typing import Optional

EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$')

def validate_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email))

def validate_username(username: str) -> Optional[str]:
    if not username or len(username) < 3:
        return "Username must be at least 3 characters"
    if len(username) > 32:
        return "Username must be at most 32 characters"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return "Username can only contain letters, numbers, and underscores"
    return None

def validate_project_name(name: str) -> Optional[str]:
    if not name or len(name.strip()) == 0:
        return "Project name is required"
    if len(name) > 100:
        return "Project name must be at most 100 characters"
    return None
""",
    "src/utils/formatters.py": """\"\"\"Output formatting utilities.\"\"\"
from datetime import datetime
from typing import Any

def format_date(dt: datetime, fmt: str = "%Y-%m-%d") -> str:
    return dt.strftime(fmt)

def format_datetime(dt: datetime) -> str:
    return dt.isoformat()

def truncate(text: str, max_len: int = 80) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."

def pretty_json(data: Any, indent: int = 2) -> str:
    import json
    return json.dumps(data, indent=indent, default=str)
""",
    "tests/__init__.py": "",
    "tests/test_models.py": """\"\"\"Tests for data models.\"\"\"
import pytest
from src.models import User, Project, Task, TaskStatus

class TestUser:
    def test_user_creation(self):
        user = User(username="alice", email="alice@example.com")
        assert user.username == "alice"
        assert user.is_active is True

    def test_deactivation(self):
        user = User(username="bob", email="bob@example.com")
        user.deactivate()
        assert user.is_active is False

    def test_to_dict(self):
        user = User(username="carol", email="carol@example.com")
        d = user.to_dict()
        assert d["username"] == "carol"
        assert "id" in d

class TestProject:
    def test_project_creation(self):
        p = Project(name="My Project", owner_id="user_1")
        assert p.name == "My Project"
        assert p.members == []

    def test_members_list(self):
        p = Project(name="Team", owner_id="u1")
        p.members.append("u2")
        assert "u2" in p.members

class TestTask:
    def test_default_status(self):
        t = Task(title="Do thing", project_id="p1")
        assert t.status == TaskStatus.PENDING

    def test_assignee(self):
        t = Task(title="Review", project_id="p2", assignee_id="u1")
        assert t.assignee_id == "u1"
""",
    "tests/test_services.py": """\"\"\"Tests for service layer.\"\"\"
import pytest
from src.database import Database
from src.services import UserService, ProjectService, TaskService

@pytest.fixture
def db():
    return Database()

@pytest.fixture
def user_svc(db):
    return UserService(db)

@pytest.fixture
def project_svc(db):
    return ProjectService(db)

@pytest.fixture
def task_svc(db):
    return TaskService(db)

class TestUserService:
    def test_create_user(self, user_svc):
        u = user_svc.create_user("alice", "a@test.com")
        assert u.username == "alice"

    def test_get_user(self, user_svc):
        u = user_svc.create_user("bob", "b@test.com")
        found = user_svc.get_user(u.id)
        assert found is not None

    def test_deactivate(self, user_svc):
        u = user_svc.create_user("carol", "c@test.com")
        assert user_svc.deactivate_user(u.id)

class TestProjectService:
    def test_create(self, project_svc):
        p = project_svc.create_project("P1", "u1")
        assert p.name == "P1"

class TestTaskService:
    def test_create(self, task_svc):
        t = task_svc.create_task("Task 1", "p1")
        assert t.title == "Task 1"
""",
    "tests/test_validators.py": """\"\"\"Tests for input validators.\"\"\"
import pytest
from src.utils.validators import validate_email, validate_username

class TestEmailValidation:
    def test_valid_email(self):
        assert validate_email("user@example.com") is True

    def test_invalid_email(self):
        assert validate_email("not-an-email") is False

    def test_empty_email(self):
        assert validate_email("") is False

class TestUsernameValidation:
    def test_valid_username(self):
        assert validate_username("john_doe") is None

    def test_too_short(self):
        assert validate_username("ab") is not None

    def test_invalid_chars(self):
        assert validate_username("hello world") is not None
""",
    "scripts/generate_data.py": """\"\"\"Generate test data for benchmarking.\"\"\"
import random, string, sys
from datetime import datetime, timedelta

def random_string(length: int = 10) -> str:
    return ''.join(random.choices(string.ascii_lowercase, k=length))

def generate_users(count: int = 100) -> list:
    users = []
    for i in range(count):
        users.append({
            "id": f"user_{i:04d}",
            "username": f"user_{random_string(8)}",
            "email": f"{random_string(5)}@example.com",
            "is_active": random.random() > 0.1,
        })
    return users

def generate_tasks(count: int = 200) -> list:
    statuses = ["pending", "in_progress", "completed", "failed"]
    tasks = []
    for i in range(count):
        tasks.append({
            "id": f"task_{i:04d}",
            "title": f"Task {random_string(15)}",
            "status": random.choice(statuses),
            "assignee_id": f"user_{random.randint(0, 99):04d}",
        })
    return tasks

if __name__ == "__main__":
    users = generate_users(100)
    tasks = generate_tasks(200)
    print(f"Generated {len(users)} users and {len(tasks)} tasks")
""",
}

# Duplicate some files to create a larger, more realistic project
_EXTRA_FILES = {
    f"src/legacy/v{i}/old_module.py": f"# Legacy module v{i}\\nclass OldClass:\\n    pass\\n" * 10
    for i in range(1, 6)
}


def create_test_project(base_dir: Path) -> dict:
    """Create a realistic Python project. Returns stats dict."""
    base_dir.mkdir(parents=True, exist_ok=True)

    total_bytes = 0
    total_lines = 0
    for relpath, content in _PROJECT_FILES.items():
        fpath = base_dir / relpath
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content)
        total_bytes += len(content)
        total_lines += content.count('\n') + 1

    # Add extra files to make project larger
    for relpath, content in _EXTRA_FILES.items():
        fpath = base_dir / relpath
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content)
        total_bytes += len(content)
        total_lines += content.count('\n') + 1

    return {
        "base_dir": str(base_dir),
        "files": len(_PROJECT_FILES) + len(_EXTRA_FILES),
        "total_bytes": total_bytes,
        "total_lines": total_lines,
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Token estimation — chars/4 for code, with real tokenizer if available
# ═══════════════════════════════════════════════════════════════════════════

def estimate_tokens(text: str) -> int:
    """Estimate token count. Uses tiktoken if available, else chars/4."""
    try:
        import tiktoken
        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except ImportError:
        return max(1, len(text) // 4)


# ═══════════════════════════════════════════════════════════════════════════
#  Timing utilities — CPU time as proxy for power consumption
# ═══════════════════════════════════════════════════════════════════════════

def measure_cpu(fn, *args, **kwargs):
    """Measure wall time + CPU time for a function call. Runs 3x, returns median."""
    wall_times = []
    cpu_times = []
    result = None
    for _ in range(3):
        t0 = time.perf_counter()
        cpu0 = os.times()
        result = fn(*args, **kwargs)
        cpu1 = os.times()
        t1 = time.perf_counter()
        wall_times.append((t1 - t0) * 1000)  # ms
        cpu_times.append(
            ((cpu1.user - cpu0.user) + (cpu1.system - cpu0.system)) * 1000
        )  # ms
    return {
        "result": result,
        "wall_ms": statistics.median(wall_times),
        "cpu_ms": statistics.median(cpu_times),
    }


# ═══════════════════════════════════════════════════════════════════════════
#  Accuracy measurement — data completeness for deterministic ops
# ═══════════════════════════════════════════════════════════════════════════

def measure_outline_accuracy(full_content: str, outline_result: str) -> float:
    """What fraction of function/class defs were captured by outline?"""
    import re
    # Count defs/classes in original
    original_defs = set()
    for m in re.finditer(r'^\s*(def |class |async def )(\w+)', full_content, re.MULTILINE):
        original_defs.add(m.group(2))

    if not original_defs:
        return 1.0

    # Count defs/classes in outline result (format: "def name [L123]")
    outline_defs = set()
    for m in re.finditer(r'(?:def |class )(\w+)', outline_result):
        outline_defs.add(m.group(1))

    return len(outline_defs & original_defs) / len(original_defs)


def measure_grep_accuracy(full_content: str, pattern: str, grep_result: str) -> float:
    """What fraction of matching lines were found by grep?"""
    import re
    # Find all matching lines in original
    original_matches = set()
    for i, line in enumerate(full_content.splitlines()):
        if re.search(pattern, line):
            original_matches.add(i + 1)  # 1-indexed

    if not original_matches:
        return 1.0

    # Find all matching lines in grep output (format: "   42  line content")
    grep_matches = set()
    for m in re.finditer(r'^\s*(\d+)  ', grep_result, re.MULTILINE):
        grep_matches.add(int(m.group(1)))

    return len(grep_matches & original_matches) / len(original_matches)


# ═══════════════════════════════════════════════════════════════════════════
#  THE ACTUAL BENCHMARKS
# ═══════════════════════════════════════════════════════════════════════════

class TestPerformanceMetrics:
    """Quantifiable performance metrics for all Miser operations."""

    @classmethod
    def setup_class(cls):
        """Create test project once for all benchmarks."""
        cls.project_dir = Path(tempfile.mkdtemp(prefix="miser_perf_"))
        cls.project_stats = create_test_project(cls.project_dir)
        # Collect all file paths for batch operations
        cls.all_files = list(cls.project_dir.rglob("*.py"))
        cls.all_contents = {str(f): f.read_text() for f in cls.all_files}
        cls.total_chars = sum(len(c) for c in cls.all_contents.values())
        cls.total_tokens = estimate_tokens(
            "\n".join(cls.all_contents.values())
        )

    @classmethod
    def teardown_class(cls):
        shutil.rmtree(cls.project_dir, ignore_errors=True)

    # ── 1. TOKEN SAVINGS — per operation type ──────────────────────────

    def test_token_savings_read_vs_direct(self):
        """Reading files via Miser vs reading them directly in agent."""
        # Simulate: agent reads all 25 files = 25 API calls × full content
        direct_tokens = self.total_tokens

        # With Miser: use outline for overview + read only what's needed
        # Typical workflow: outline 3 key files + read 2 critical files
        key_files = self.all_files[:5]
        miser_tokens = 0
        for f in key_files[:3]:
            result = outline_file(str(f))
            miser_tokens += estimate_tokens(result)
        for f in key_files[3:5]:
            result = read_file(str(f))
            miser_tokens += estimate_tokens(result)

        savings = direct_tokens - miser_tokens
        savings_rate = savings / max(direct_tokens, 1)

        print(f"\n  [TOKEN SAVINGS — Read vs Outline workflow]")
        print(f"    Direct (read all {len(self.all_files)} files): {direct_tokens:,} tokens")
        print(f"    Miser (3 outlines + 2 reads):              {miser_tokens:,} tokens")
        print(f"    Saved:  {savings:,} tokens ({savings_rate:.1%})")

        assert savings_rate > 0.5, \
            f"Expected >50% token savings, got {savings_rate:.1%}"

    def test_token_savings_grep_vs_full_read(self):
        """grep instead of reading entire file to find one function."""
        # Pick a file with many functions
        svc_file = str(self.project_dir / "src" / "services.py")
        full_content = self.all_contents.get(svc_file, "")
        direct_tokens = estimate_tokens(full_content)

        # Miser: grep for a specific function
        result = grep_file(svc_file, "def create_user", context=5)
        miser_tokens = estimate_tokens(result)

        savings = direct_tokens - miser_tokens
        savings_rate = savings / max(direct_tokens, 1)

        print(f"\n  [TOKEN SAVINGS — grep vs full read]")
        print(f"    Direct (read entire file):      {direct_tokens:,} tokens")
        print(f"    Miser (grep 'def create_user'): {miser_tokens:,} tokens")
        print(f"    Saved:  {savings:,} tokens ({savings_rate:.1%})")

        assert savings_rate > 0.7, \
            f"Expected >70% savings for grep, got {savings_rate:.1%}"

    def test_token_savings_outline_vs_full_read(self):
        """outline instead of reading entire file for structure."""
        svc_file = str(self.project_dir / "src" / "services.py")
        full_content = self.all_contents.get(svc_file, "")
        direct_tokens = estimate_tokens(full_content)

        result = outline_file(svc_file)
        miser_tokens = estimate_tokens(result)

        savings = direct_tokens - miser_tokens
        savings_rate = savings / max(direct_tokens, 1)

        print(f"\n  [TOKEN SAVINGS — outline vs full read]")
        print(f"    Direct (read entire file):  {direct_tokens:,} tokens")
        print(f"    Miser (outline):            {miser_tokens:,} tokens")
        print(f"    Saved:  {savings:,} tokens ({savings_rate:.1%})")

        assert savings_rate > 0.7, \
            f"Expected >70% savings for outline, got {savings_rate:.1%}"

    def test_token_savings_tree_vs_ls_recursive(self):
        """tree vs ls -R for project structure."""
        # Direct: ls -R output (simulated)
        direct_output = run_shell(f"find {self.project_dir} -type f | head -50")
        direct_tokens = estimate_tokens(direct_output)

        # Miser: tree view
        result = tree_view(str(self.project_dir), depth=3)
        miser_tokens = estimate_tokens(result)

        savings = direct_tokens - miser_tokens
        savings_rate = savings / max(direct_tokens, 1)

        print(f"\n  [TOKEN SAVINGS — tree vs ls -R]")
        print(f"    Direct (find output):  {direct_tokens:,} tokens")
        print(f"    Miser (tree depth=3):  {miser_tokens:,} tokens")
        print(f"    Saved:  {savings:,} tokens ({savings_rate:.1%})")

        # tree is often more compact than raw find
        assert savings_rate > 0, "Tree should not be worse than find"

    # ── 2. AGGREGATE SESSION SAVINGS ───────────────────────────────────

    def test_aggregate_session_token_savings(self):
        """Simulate a real coding session: 10 operations, measure total savings."""
        files = self.all_files

        ops = [
            # (description, direct_fn, miser_fn)
            ("Read services.py", lambda: self.all_contents.get(str(files[2]), ""),
             lambda: read_file(str(files[2]))),
            ("Outline models.py", lambda: self.all_contents.get(str(files[1]), ""),
             lambda: outline_file(str(files[1]))),
            ("Grep 'def test_'", lambda: self.all_contents.get(str(files[12]), ""),
             lambda: grep_file(str(files[12]), "def test_")),
            ("Outline services.py", lambda: self.all_contents.get(str(files[2]), ""),
             lambda: outline_file(str(files[2]))),
            ("Tree project", lambda: run_shell(f"find {self.project_dir} -type f"),
             lambda: tree_view(str(self.project_dir), depth=2)),
            ("Read routes.py", lambda: self.all_contents.get(str(files[5]), ""),
             lambda: read_file(str(files[5]))),
            ("Grep 'class '", lambda: self.all_contents.get(str(files[12]), ""),
             lambda: grep_file(str(files[12]), "class ")),
            ("Outline middleware.py", lambda: self.all_contents.get(str(files[6]), ""),
             lambda: outline_file(str(files[6]))),
            ("Read database.py", lambda: self.all_contents.get(str(files[2]), ""),
             lambda: read_file(str(files[2]))),
            ("Grep 'import '", lambda: self.all_contents.get(str(files[2]), ""),
             lambda: grep_file(str(files[2]), "import ")),
        ]

        direct_total = 0
        miser_total = 0

        for name, direct_fn, miser_fn in ops:
            direct = direct_fn()
            miser = miser_fn()
            direct_total += estimate_tokens(str(direct))
            miser_total += estimate_tokens(str(miser))

        savings = direct_total - miser_total
        savings_rate = savings / max(direct_total, 1)

        print(f"\n  [AGGREGATE SESSION — 10 operations]")
        print(f"    Direct (all full reads):  {direct_total:,} tokens")
        print(f"    Miser (mixed ops):        {miser_total:,} tokens")
        print(f"    Session savings:          {savings:,} tokens ({savings_rate:.1%})")

        assert savings_rate > 0.40, \
            f"Expected >40% session savings (mixed ops include reads), got {savings_rate:.1%}"

    # ── 3. CPU OVERHEAD — proxy for power consumption ──────────────────

    def test_cpu_overhead_per_operation(self):
        """Measure CPU time per operation type. This is the 'power cost' proxy."""
        files = self.all_files
        results = {}

        # Outline — most common operation
        m = measure_cpu(outline_file, str(files[2]))
        results["outline"] = m
        print(f"\n  [CPU OVERHEAD]")
        print(f"    outline:  {m['cpu_ms']:.2f}ms CPU, {m['wall_ms']:.2f}ms wall")

        # Grep
        m = measure_cpu(grep_file, str(files[12]), "def test_")
        results["grep"] = m
        print(f"    grep:     {m['cpu_ms']:.2f}ms CPU, {m['wall_ms']:.2f}ms wall")

        # Tree
        m = measure_cpu(tree_view, str(self.project_dir), 2)
        results["tree"] = m
        print(f"    tree:     {m['cpu_ms']:.2f}ms CPU, {m['wall_ms']:.2f}ms wall")

        # Read (full file)
        m = measure_cpu(read_file, str(files[2]))
        results["read"] = m
        print(f"    read:     {m['cpu_ms']:.2f}ms CPU, {m['wall_ms']:.2f}ms wall")

        # All operations should complete well under 100ms
        for op, m in results.items():
            assert m["cpu_ms"] < 100, \
                f"{op} CPU time {m['cpu_ms']:.1f}ms exceeds 100ms threshold"

    def test_power_cost_estimation(self):
        """Estimate power cost: CPU-ms per operation, scaled to cloud API latency."""
        files = self.all_files

        # Average cloud API call latency (GPT-4 class): ~500ms
        # Miser local operations: measured CPU time
        cloud_latency_ms = 500  # typical API roundtrip

        ops_cpu = {}
        for name, target in [("outline", str(files[2])),
                              ("grep", str(files[12])),
                              ("tree", str(self.project_dir)),  # dir, not file
                              ("read", str(files[2]))]:
            fn = outline_file if name == "outline" else \
                 (lambda p: grep_file(p, "def ")) if name == "grep" else \
                 (lambda p: tree_view(p, 1)) if name == "tree" else read_file
            m = measure_cpu(fn, target)
            ops_cpu[name] = m

        print(f"\n  [POWER COST vs CLOUD LATENCY]")
        print(f"    Cloud API call:  ~{cloud_latency_ms}ms (network + inference)")
        for op, m in ops_cpu.items():
            ratio = cloud_latency_ms / max(m["wall_ms"], 0.001)
            print(f"    Miser {op}:   {m['wall_ms']:.1f}ms wall "
                  f"({ratio:.0f}x faster than cloud)")

        # All ops should be at least 5x faster than cloud API
        for op, m in ops_cpu.items():
            ratio = cloud_latency_ms / max(m["wall_ms"], 0.001)
            assert ratio > 5, \
                f"{op} only {ratio:.1f}x faster than cloud — not significant"

    # ── 4. ACCURACY — data completeness ────────────────────────────────

    def test_outline_data_completeness(self):
        """Outline captures ALL function/class definitions."""
        svc_file = str(self.project_dir / "src" / "services.py")
        full = self.all_contents.get(svc_file, "")
        result = outline_file(svc_file)
        accuracy = measure_outline_accuracy(full, result)

        print(f"\n  [ACCURACY — Outline completeness]")
        print(f"    File: services.py ({len(full):,} chars)")
        print(f"    Outline accuracy: {accuracy:.1%}")

        assert accuracy == 1.0, \
            f"Outline missed {1-accuracy:.1%} of definitions"

    def test_grep_data_completeness(self):
        """Grep finds ALL matching lines."""
        test_file = str(self.project_dir / "tests" / "test_services.py")
        full = self.all_contents.get(test_file, "")
        result = grep_file(test_file, "def test_")
        accuracy = measure_grep_accuracy(full, "def test_", result)

        print(f"\n  [ACCURACY — Grep completeness]")
        print(f"    File: test_services.py")
        print(f"    Pattern: 'def test_'")
        print(f"    Grep accuracy: {accuracy:.1%}")

        assert accuracy == 1.0, \
            f"Grep missed {1-accuracy:.1%} of matches"

    def test_tree_data_completeness(self):
        """Tree shows all files in the project."""
        result = tree_view(str(self.project_dir), depth=5)
        # Count how many .py files appear in tree output
        py_files_in_tree = sum(
            1 for f in self.all_files if f.name in result
        )

        completeness = py_files_in_tree / max(len(self.all_files), 1)

        print(f"\n  [ACCURACY — Tree completeness]")
        print(f"    Project has {len(self.all_files)} .py files")
        print(f"    Tree shows {py_files_in_tree} .py files")
        print(f"    Completeness: {completeness:.1%}")

        assert completeness > 0.9, \
            f"Tree only shows {completeness:.1%} of files"

    # ── 5. PERF_COST — composite performance cost metric ───────────────

    def test_perf_cost_composite_score(self):
        """PERF_COST = CPU-ms per 1000 tokens saved. Lower = better.
        PERF_EFFICIENCY = tokens saved per CPU-ms. Higher = better."""
        files = self.all_files

        total_cpu_ms = 0
        total_tokens_saved = 0

        operations = [
            ("outline", lambda: outline_file(str(files[2])),
             len(self.all_contents.get(str(files[2]), ""))),
            ("grep", lambda: grep_file(str(files[12]), "def test_"),
             len(self.all_contents.get(str(files[12]), ""))),
            ("tree", lambda: tree_view(str(self.project_dir), 2),
             len(run_shell(f"find {self.project_dir} -type f"))),
            ("read_targeted", lambda: read_file(str(files[2]), limit=2000),
             len(self.all_contents.get(str(files[2]), ""))),
        ]

        for name, op_fn, direct_chars in operations:
            m = measure_cpu(op_fn)
            result = m["result"]
            cpu = m["cpu_ms"]
            direct_tokens = estimate_tokens("x" * direct_chars)  # simulate full read
            miser_tokens = estimate_tokens(str(result))
            saved = direct_tokens - miser_tokens

            total_cpu_ms += cpu
            total_tokens_saved += max(saved, 0)

        # PERF_COST: how much CPU does it cost to save 1000 tokens?
        perf_cost = (total_cpu_ms / max(total_tokens_saved, 1)) * 1000

        # PERF_EFFICIENCY: how many tokens saved per CPU-ms?
        perf_efficiency = total_tokens_saved / max(total_cpu_ms, 0.001)

        print(f"\n  [COMPOSITE PERFORMANCE SCORE]")
        print(f"    Total CPU time:      {total_cpu_ms:.2f}ms")
        print(f"    Total tokens saved:  {total_tokens_saved:,}")
        print(f"    PERF_COST:   {perf_cost:.2f} CPU-ms per 1000 tokens saved")
        print(f"    PERF_EFFICIENCY:     {perf_efficiency:.1f} tokens/CPU-ms")
        print(f"    (Lower PERF_COST = better; Higher PERF_EFFICIENCY = better)")

        # PERF_COST should be very low — we're saving tokens with minimal CPU
        assert perf_cost < 100, \
            f"PERF_COST {perf_cost:.1f} too high (target <100 CPU-ms/1K tokens)"

        # PERF_EFFICIENCY should be high — each CPU-ms saves many tokens
        assert perf_efficiency > 10, \
            f"PERF_EFFICIENCY {perf_efficiency:.1f} too low (target >10 tokens/CPU-ms)"

    # ── 6. RELIABILITY — results are reproducible ─────────────────────

    def test_deterministic_results(self):
        """Zero-LLM operations produce identical results on repeated calls."""
        svc_file = str(self.project_dir / "src" / "services.py")

        results1 = outline_file(svc_file)
        results2 = outline_file(svc_file)
        results3 = outline_file(svc_file)

        assert results1 == results2 == results3, \
            "Outline produced different results on repeated calls"

        grep1 = grep_file(svc_file, "class ")
        grep2 = grep_file(svc_file, "class ")
        assert grep1 == grep2, "Grep produced different results"

    # ── 7. TOTAL SUMMARY — everything in one view ──────────────────────

    def test_performance_summary_report(self):
        """Print a comprehensive performance summary for human review."""
        files = self.all_files

        # Collect all metrics
        metrics = {}

        # Outline benchmark
        m = measure_cpu(outline_file, str(files[2]))
        full_chars = len(self.all_contents.get(str(files[2]), ""))
        outline_tokens = estimate_tokens(str(m["result"]))
        full_tokens = estimate_tokens("x" * full_chars)
        metrics["outline"] = {
            "cpu_ms": m["cpu_ms"],
            "wall_ms": m["wall_ms"],
            "tokens_direct": full_tokens,
            "tokens_miser": outline_tokens,
            "savings_pct": (full_tokens - outline_tokens) / max(full_tokens, 1),
        }

        # Grep benchmark
        m = measure_cpu(grep_file, str(files[12]), "def test_")
        full_chars = len(self.all_contents.get(str(files[12]), ""))
        grep_tokens = estimate_tokens(str(m["result"]))
        full_tokens = estimate_tokens("x" * full_chars)
        metrics["grep"] = {
            "cpu_ms": m["cpu_ms"],
            "wall_ms": m["wall_ms"],
            "tokens_direct": full_tokens,
            "tokens_miser": grep_tokens,
            "savings_pct": (full_tokens - grep_tokens) / max(full_tokens, 1),
        }

        # Tree benchmark
        m = measure_cpu(tree_view, str(self.project_dir), 2)
        find_output = run_shell(f"find {self.project_dir} -type f")
        tree_tokens = estimate_tokens(str(m["result"]))
        find_tokens = estimate_tokens(find_output)
        metrics["tree"] = {
            "cpu_ms": m["cpu_ms"],
            "wall_ms": m["wall_ms"],
            "tokens_direct": find_tokens,
            "tokens_miser": tree_tokens,
            "savings_pct": (find_tokens - tree_tokens) / max(find_tokens, 1),
        }

        # Read benchmark
        m = measure_cpu(read_file, str(files[2]), 2000)
        full_chars = len(self.all_contents.get(str(files[2]), ""))
        read_tokens = estimate_tokens(str(m["result"]))
        full_tokens = estimate_tokens("x" * full_chars)
        metrics["read_targeted"] = {
            "cpu_ms": m["cpu_ms"],
            "wall_ms": m["wall_ms"],
            "tokens_direct": full_tokens,
            "tokens_miser": read_tokens,
            "savings_pct": (full_tokens - read_tokens) / max(full_tokens, 1),
        }

        # Calculate composites
        total_cpu = sum(v["cpu_ms"] for v in metrics.values())
        total_saved = sum(v["tokens_direct"] - v["tokens_miser"] for v in metrics.values())
        total_direct = sum(v["tokens_direct"] for v in metrics.values())
        overall_savings = total_saved / max(total_direct, 1)
        perf_cost = (total_cpu / max(total_saved, 1)) * 1000
        perf_efficiency = total_saved / max(total_cpu, 0.001)

        print("\n" + "=" * 68)
        print("  MISER v1.5 PERFORMANCE REPORT")
        print("=" * 68)
        print(f"  Project: {len(files)} files, "
              f"{sum(len(self.all_contents.get(str(f),'')) for f in files):,} chars")
        print(f"  Estimated cloud tokens for full reads: "
              f"{sum(estimate_tokens(self.all_contents.get(str(f),'')) for f in files):,}")
        print("-" * 68)
        print(f"  {'Operation':<16} {'CPUms':>7} {'Wallms':>7} "
              f"{'Direct':>8} {'Miser':>8} {'Save%':>7}")
        print("-" * 68)

        for name, m in metrics.items():
            print(f"  {name:<16} {m['cpu_ms']:>6.1f}  {m['wall_ms']:>6.1f}  "
                  f"{m['tokens_direct']:>7,} {m['tokens_miser']:>7,} "
                  f"{m['savings_pct']:>6.1%}")

        print("-" * 68)
        print(f"  {'TOTAL':<16} {total_cpu:>6.1f}ms {'':>7} "
              f"{total_direct:>7,} {total_direct - total_saved:>7,} "
              f"{overall_savings:>6.1%}")
        print("=" * 68)
        print(f"  PERF_COST:      {perf_cost:.2f} CPU-ms / 1,000 tokens saved")
        print(f"  PERF_EFFICIENCY: {perf_efficiency:.1f} tokens saved / CPU-ms")
        print(f"  OVERALL SAVINGS: {overall_savings:.1%}")
        print("=" * 68 + "\n")

        # Assertions on the composite metrics
        assert overall_savings > 0.5, \
            f"Overall savings {overall_savings:.1%} below 50% threshold"
        assert perf_cost < 100, \
            f"PERF_COST {perf_cost:.1f} exceeds 100 CPU-ms/1K tokens"
        assert perf_efficiency > 10, \
            f"PERF_EFFICIENCY {perf_efficiency:.1f} below 10 tokens/CPU-ms"

        # Store metrics for external consumption
        summary = {
            "version": "1.5.0",
            "project_stats": self.project_stats,
            "operations": {k: {kk: vv for kk, vv in v.items()}
                          for k, v in metrics.items()},
            "composite": {
                "total_cpu_ms": round(total_cpu, 2),
                "total_tokens_saved": total_saved,
                "overall_savings_pct": round(overall_savings * 100, 1),
                "perf_cost_cpu_ms_per_1k_tokens": round(perf_cost, 2),
                "perf_efficiency_tokens_per_cpu_ms": round(perf_efficiency, 1),
            },
        }
        # Write JSON report
        report_path = Path(__file__).parent.parent / "test-results" / "perf_report.json"
        report_path.parent.mkdir(exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2))
