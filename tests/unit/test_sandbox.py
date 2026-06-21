"""
Sandbox unit tests — 8 adversarial cases.

These tests run the import-check layer only (no subprocess) so they're fast
and don't require a real CSV file.
"""

from app.tools.sandbox import _check_imports

# ── Import allowlist ──────────────────────────────────────────────────────────


def test_allowed_imports_pass():
    code = "import pandas as pd\nimport numpy as np\nimport matplotlib.pyplot as plt"
    assert _check_imports(code) == []


def test_disallowed_os_system():
    code = "import subprocess"
    banned = _check_imports(code)
    assert "subprocess" in banned


def test_disallowed_socket():
    code = "import socket"
    banned = _check_imports(code)
    assert "socket" in banned


def test_disallowed_requests():
    code = "import requests"
    banned = _check_imports(code)
    assert "requests" in banned


def test_disallowed_shutil():
    code = "import shutil"
    banned = _check_imports(code)
    assert "shutil" in banned


def test_disallowed_from_import():
    code = "from urllib.request import urlopen"
    banned = _check_imports(code)
    assert any("urllib" in b for b in banned)


def test_disallowed_boto3():
    code = "import boto3"
    banned = _check_imports(code)
    assert "boto3" in banned


def test_allowed_from_pandas():
    code = "from pandas import DataFrame\nfrom numpy import mean"
    assert _check_imports(code) == []


# ── Syntax error doesn't crash checker ───────────────────────────────────────


def test_syntax_error_returns_empty():
    code = "def broken(:\n  pass"
    result = _check_imports(code)
    assert isinstance(result, list)


# ── Cost tracker ──────────────────────────────────────────────────────────────


def test_cost_tracker_calculation():
    from app.utils.cost_tracker import RunCostTracker

    tracker = RunCostTracker()
    tracker.record("gpt-4o", input_tokens=1_000_000, output_tokens=0)
    assert abs(tracker.total_cost_usd - 2.50) < 0.01


def test_cost_tracker_multi_model():
    from app.utils.cost_tracker import RunCostTracker

    tracker = RunCostTracker()
    tracker.record("gpt-4o", input_tokens=500_000, output_tokens=100_000)
    tracker.record("claude-sonnet-4-6", input_tokens=200_000, output_tokens=50_000)
    summary = tracker.summary()
    assert summary["total_cost_usd"] > 0
    assert len(summary["by_model"]) == 2


# ── Prompt loader ─────────────────────────────────────────────────────────────


def test_prompt_loader_missing_returns_default():
    from app.utils.prompt_loader import load_prompt_safe

    result = load_prompt_safe("nonexistent_prompt", default="fallback")
    assert result == "fallback"


def test_prompt_loader_loads_existing():
    from app.utils.prompt_loader import load_prompt

    text = load_prompt("goal_parser")
    assert len(text) > 10
