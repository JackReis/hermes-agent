"""Run with .venv/bin/python; each guard mutation uses an isolated source copy."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


MUTATIONS = {
    "actor": ("if user_id != pending.source.user_id:", "if False:", "test_rejects_cross_scope_callback"),
    "thread": (
        'or (message.get("thread_ts") or "") != pending.thread_id',
        "or False", "test_rejects_cross_scope_callback",
    ),
    "card": ('or message.get("ts") != pending.card_id', "or False", "test_rejects_cross_scope_callback"),
    "exec_subject": (
        "native not in queue or native.data != pending.subject", "native not in queue",
        "test_rejects_stale_request",
    ),
    "confirm_request": (
        "native is not pending.native_request or native != pending.subject", "False",
        "test_rejects_stale_request",
    ),
    "authorization": ("self._authorized(adapter, pending.source)", "True", "test_rejects_stale_request"),
    "session": (
        "and self._session(adapter, pending.source, pending.session_key) == pending.session_id",
        "and True", "test_rejects_stale_request",
    ),
}


def run(work: Path, selector: str = "") -> subprocess.CompletedProcess:
    command = ["bash", "scripts/run_tests.sh", "-j", "1", "tests/gateway/test_slack_interaction_binding.py"]
    if selector:
        command += ["--", "-k", selector]
    return subprocess.run(command, cwd=work, capture_output=True, text=True, encoding="utf-8", timeout=120)


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    helper = Path("gateway/platforms/slack_interactions.py")
    original = (repo / helper).read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="hermes-slack-mutations-") as directory:
        work = Path(directory)
        for child in repo.iterdir():
            if child.name.startswith(".") and child.name != ".venv":
                continue
            target = work / child.name
            if child.name in {"gateway", "tests", "scripts"}:
                shutil.copytree(child, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            else:
                target.symlink_to(child, target_is_directory=child.is_dir())
        result = run(work)
        if result.returncode:
            print("BASELINE FAILED\n" + result.stdout + result.stderr)
            return 1
        print("Baseline: behavioral tests passed", flush=True)
        for name, (before, after, selector) in MUTATIONS.items():
            if original.count(before) != 1:
                raise RuntimeError(f"Mutation {name} no longer matches exactly one guard")
            (work / helper).write_text(original.replace(before, after), encoding="utf-8")
            shutil.rmtree(work / "gateway/platforms/__pycache__", ignore_errors=True)
            result = run(work, selector)
            # A collection/import/tooling failure is not a killed behavioral mutation.
            if (result.returncode != 1 or "AssertionError" not in result.stdout
                    or f"FAILED tests/gateway/test_slack_interaction_binding.py::{selector}" not in result.stdout):
                print(f"SURVIVED or invalid failure: {name}\n{result.stdout}\n{result.stderr}")
                return 1
            print(f"KILLED: {name} (native waiter/Slack side-effect assertion failed)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
