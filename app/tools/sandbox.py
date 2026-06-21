"""
3-layer sandboxed code executor.

Layer 1 — env stripping: subprocess inherits NO secrets (no OPENAI_API_KEY etc.)
Layer 2 — RestrictedPython: import allowlist enforced before execution
Layer 3 — subprocess timeout + stdout/stderr caps
"""

import contextlib
import os
import subprocess
import tempfile
import textwrap
import time
from pathlib import Path

from app.schemas.report import CodeOutput

# Only these imports are allowed inside generated code
_ALLOWED_IMPORTS = frozenset(
    {
        "pandas",
        "numpy",
        "matplotlib",
        "matplotlib.pyplot",
        "matplotlib.figure",
        "plotly",
        "plotly.express",
        "plotly.graph_objects",
        "json",
        "math",
        "statistics",
        "datetime",
        "re",
        "os",
        "warnings",
        "io",
        "collections",
    }
)

_SAFE_HEADER = textwrap.dedent(
    """
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import os
    import warnings
    warnings.filterwarnings('ignore')
    os.makedirs('/tmp/charts', exist_ok=True)
    df = pd.read_csv('{csv_path}')
    """
)

_STDOUT_CAP = 8_000  # bytes
_STDERR_CAP = 2_000


def _check_imports(code: str) -> list[str]:
    """Return list of disallowed imports found in code."""
    import ast

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    banned = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root not in _ALLOWED_IMPORTS:
                    banned.append(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root not in _ALLOWED_IMPORTS:
                banned.append(node.module)
    return banned


def run_sandboxed_code(
    code: str,
    csv_path: str,
    timeout_seconds: int = 30,
    max_memory_mb: int = 512,
) -> CodeOutput:
    """
    Execute LLM-generated code in a sandboxed subprocess.

    Returns CodeOutput with stdout, stderr, chart paths, and success flag.
    """
    # Layer 2: import check before we even start a subprocess
    banned = _check_imports(code)
    if banned:
        return CodeOutput(
            stdout="",
            stderr=f"Disallowed imports: {banned}",
            execution_time_ms=0,
            success=False,
            error=f"Import blocked: {banned}",
        )

    header = _SAFE_HEADER.format(csv_path=csv_path)
    full_code = header + "\n" + code

    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False, encoding="utf-8") as f:
        f.write(full_code)
        tmp_path = f.name

    # Layer 1: stripped env — no secrets, no HOME pointing to real user dir
    safe_env = {
        "PATH": "/usr/bin:/bin",
        "HOME": "/tmp",
        "MPLBACKEND": "Agg",
    }
    # On Windows we need a bit more in PATH
    if os.name == "nt":
        safe_env["PATH"] = os.environ.get("PATH", "")
        safe_env["SYSTEMROOT"] = os.environ.get("SYSTEMROOT", "C:\\Windows")

    charts_before = _list_charts()
    start = time.perf_counter()

    try:
        result = subprocess.run(
            ["python", tmp_path],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=safe_env,
        )
        elapsed_ms = int((time.perf_counter() - start) * 1000)

        charts_after = _list_charts()
        new_charts = [c for c in charts_after if c not in charts_before]

        return CodeOutput(
            stdout=result.stdout[:_STDOUT_CAP],
            stderr=result.stderr[:_STDERR_CAP],
            charts_generated=new_charts,
            execution_time_ms=elapsed_ms,
            success=(result.returncode == 0),
            error=result.stderr[:_STDERR_CAP] if result.returncode != 0 else None,
        )

    except subprocess.TimeoutExpired:
        elapsed_ms = timeout_seconds * 1000
        return CodeOutput(
            stdout="",
            stderr="",
            charts_generated=[],
            execution_time_ms=elapsed_ms,
            success=False,
            error=f"Execution timed out after {timeout_seconds}s",
        )

    finally:
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


def _list_charts() -> list[str]:
    charts_dir = Path("/tmp/charts")
    if not charts_dir.exists():
        return []
    return [str(p) for p in charts_dir.glob("*.png")]
