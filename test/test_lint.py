"""
Single test-case, just confirms the code is linted.
"""

import subprocess

from util.git import get_git_root


def test_lint():
    subprocess.run(["uv", "run", "ruff", "check", get_git_root()], check=True)
