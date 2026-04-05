"""Environment auto-detection for all CLI entry points.

Environment is strictly determined by git branch/tag or binary type.
No manual override is permitted — this is the single source of truth.

Detection rules:
  frozen binary        → prod  (release build, always production)
  tagged commit (main) → prod  (tagged release)
  main branch          → int   (integration / paper trading)
  any other branch     → dev   (local development, mock API)
  no git repo          → prod  (safe fallback)
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent


def detect_env() -> str:
    """Return the environment string derived from git state or binary context.

    Returns:
        One of ``"dev"``, ``"int"``, or ``"prod"``.
    """
    if getattr(sys, "frozen", False):
        return "prod"

    try:
        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=_ROOT,
            timeout=5,
        )
        if branch.returncode != 0:
            return "prod"

        branch_name = branch.stdout.strip()

        if branch_name == "main":
            tag = subprocess.run(
                ["git", "describe", "--exact-match", "HEAD"],
                capture_output=True,
                text=True,
                cwd=_ROOT,
                timeout=5,
            )
            return "prod" if tag.returncode == 0 else "int"

        return "dev"
    except Exception:
        return "prod"


def set_env() -> str:
    """Detect environment and export it as ``ENVIRONMENT``, then return it.

    Idempotent: if ``ENVIRONMENT`` is already set (e.g. by a parent process
    that also used this module), the existing value is preserved and returned.
    """
    if "ENVIRONMENT" not in os.environ:
        os.environ["ENVIRONMENT"] = detect_env()
    return os.environ["ENVIRONMENT"]
