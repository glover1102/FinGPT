from __future__ import annotations

import os
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_info() -> dict[str, Any]:
    """Return a lightweight code identity payload without requiring git."""

    return {
        "build_id": os.getenv("FINGPT_BUILD_ID") or _git_commit(short=True) or "local-unversioned",
        "git_commit": os.getenv("FINGPT_GIT_COMMIT") or _git_commit(short=False),
        "git_branch": os.getenv("FINGPT_GIT_BRANCH") or _git_branch(),
        "source": "env_or_local_git",
    }


def _git_branch() -> str | None:
    head = PROJECT_ROOT / ".git" / "HEAD"
    try:
        text = head.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if text.startswith("ref:"):
        return text.rsplit("/", 1)[-1].strip() or None
    return "detached"


def _git_commit(*, short: bool) -> str | None:
    head = PROJECT_ROOT / ".git" / "HEAD"
    try:
        text = head.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    commit: str | None = None
    if text.startswith("ref:"):
        ref = text.split(":", 1)[1].strip()
        ref_path = PROJECT_ROOT / ".git" / ref
        try:
            commit = ref_path.read_text(encoding="utf-8").strip()
        except OSError:
            commit = _packed_ref(ref)
    else:
        commit = text
    if not commit:
        return None
    return commit[:12] if short else commit


def _packed_ref(ref: str) -> str | None:
    packed = PROJECT_ROOT / ".git" / "packed-refs"
    try:
        lines = packed.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if not line or line.startswith("#") or line.startswith("^"):
            continue
        commit, _, name = line.partition(" ")
        if name.strip() == ref:
            return commit.strip()
    return None
