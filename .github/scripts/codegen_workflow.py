#!/usr/bin/env python3
"""Helper script for the Codegen workflow."""

from __future__ import annotations

import argparse
import glob
import json
import os
import pathlib
import re
import sys
import time
from typing import Any, Dict


def _write_output_lines(lines: Dict[str, str]) -> None:
    """Append key/value pairs to the GITHUB_OUTPUT file."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        raise SystemExit("::error::GITHUB_OUTPUT environment variable is not set.")
    path = pathlib.Path(output_path)
    with path.open("a", encoding="utf-8") as handle:
        for key, value in lines.items():
            handle.write(f"{key}={value}\n")


def cmd_prepare_prompt() -> None:
    env = os.environ

    def read_text(path: pathlib.Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            raise SystemExit(f"::error::Failed to read spec '{path}': {exc}") from exc

    prompt = env.get("INPUT_PROMPT", "")
    source = "input" if prompt else ""
    candidate: pathlib.Path | None = None

    if not prompt:
        requested = env.get("INPUT_SPEC_PATH", "").strip()
        if requested:
            requested_path = pathlib.Path(requested)
            if requested_path.exists():
                candidate = requested_path
            else:
                print(f"::warning::Requested spec_path '{requested}' not found.")
        globs: list[str] = []
        custom_glob = env.get("INPUT_SPECS_GLOB", "").strip()
        if custom_glob:
            globs.append(custom_glob)
        globs.extend([".agent-os/specs/**/*", ".specify/specs/**/*"])
        if candidate is None:
            newest: pathlib.Path | None = None
            newest_mtime = -1.0
            for pattern in globs:
                for match in glob.glob(pattern, recursive=True):
                    path = pathlib.Path(match)
                    if not path.is_file():
                        continue
                    mtime = path.stat().st_mtime
                    if mtime > newest_mtime:
                        newest_mtime = mtime
                        newest = path
            if newest is not None:
                candidate = newest
        if candidate is not None:
            prompt = (
                f"Follow the latest specification at {candidate.as_posix()}\n\n"
                + read_text(candidate)
            )
            print(
                f"::notice::Using spec '{candidate.as_posix()}' for prompt generation."
            )
            source = "spec"
        else:
            prompt = (
                "No specification was discovered. Inspect the repository and proceed "
                "safely."
            )
            print("::warning::No specification files found; using fallback guidance prompt.")
            source = "fallback"

    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        raise SystemExit("::error::GITHUB_OUTPUT environment variable is not set.")
    path = pathlib.Path(output_path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write("prompt<<EOF\n")
        handle.write(prompt)
        handle.write("\nEOF\n")
        handle.write(f"prompt-source={source}\n")


def _load_result_payload(result: Any) -> Dict[str, Any]:
    if isinstance(result, dict):
        return dict(result)
    if hasattr(result, "__dict__"):
        return dict(getattr(result, "__dict__"))
    return {"value": str(result)}


def cmd_run_task() -> None:
    env = os.environ
    resolved_repo_id = env.get("RESOLVED_REPO_ID", "").strip()
    if not resolved_repo_id:
        print("::error::Resolved repository id is empty.")
        raise SystemExit(1)

    try:
        from codegen import Agent  # type: ignore import-not-found
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"::error::Failed to import Codegen Agent: {exc}") from exc

    agent = Agent(org_id=env["CODEGEN_ORG_ID"], token=env["CODEGEN_TOKEN"])
    prompt = env.get("PROMPT", "")

    try:
        result = agent.run(prompt=prompt)
    except Exception as exc:  # noqa: BLE001
        message = str(exc)
        if "401" in message or "Unauthorized" in message:
            print(
                "::error::Unauthorized: verify CODEGEN_ORG_ID/CODEGEN_TOKEN secrets and repository permissions."
            )
        raise

    payload = _load_result_payload(result)
    outputs: Dict[str, str] = {}
    for key in ("task_id", "id", "status", "pr_url"):
        value = payload.get(key)
        if value:
            outputs[key] = str(value)
    if "task_id" not in outputs and "id" in outputs:
        outputs["task_id"] = outputs["id"]

    _write_output_lines(outputs)
    print("::notice::Submitted Codegen task.")


def cmd_wait_task() -> None:
    env = os.environ
    resolved_repo_id = env.get("RESOLVED_REPO_ID", "").strip()
    if not resolved_repo_id:
        print("::error::Resolved repository id is empty.")
        raise SystemExit(1)

    try:
        from codegen import Agent  # type: ignore import-not-found
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"::error::Failed to import Codegen Agent: {exc}") from exc

    agent = Agent(org_id=env["CODEGEN_ORG_ID"], token=env["CODEGEN_TOKEN"])
    task_id = env.get("TASK_ID", "").strip()
    if not task_id:
        print("::error::TASK_ID is required to wait for task completion.")
        raise SystemExit(1)

    status: str | None = None
    pr_url: str | None = None
    pending = {"pending", "queued", "in_progress", "running"}
    deadline = time.time() + 1800

    while time.time() < deadline:
        try:
            detail = agent.get_task(task_id)  # type: ignore[attr-defined]
        except AttributeError:
            print("::warning::Agent.get_task is unavailable; cannot poll task status.")
            break
        except Exception as exc:  # noqa: BLE001
            print(f"::warning::Failed to poll task: {exc}")
            time.sleep(15)
            continue

        if not isinstance(detail, dict):
            print("::warning::Unexpected task detail payload; stopping poll.")
            break

        status = detail.get("status") or status
        pr_url = detail.get("pr_url") or pr_url
        if status and status.lower() not in pending:
            break
        time.sleep(15)
    else:
        print("::warning::Polling timed out before task completed.")

    output: Dict[str, str] = {}
    if status:
        output["status"] = str(status)
    if pr_url:
        output["pr_url"] = str(pr_url)
    if output:
        _write_output_lines(output)


def cmd_validate_pr() -> None:
    env = os.environ
    target_repo = env.get("TARGET_REPO", "").strip()
    pr_url = env.get("PR_URL_WAIT", "").strip() or env.get("PR_URL_INITIAL", "").strip()

    if not pr_url:
        print("::notice::No pull request URL provided by Codegen.")
        return

    match = re.match(r"https://github\.com/([^/]+/[^/]+)/pull/\d+", pr_url)
    if not match:
        raise SystemExit("::error::Invalid pull request URL returned by Codegen.")

    repo = match.group(1)
    if target_repo and repo.lower() != target_repo.lower():
        raise SystemExit(
            f"::error::Codegen created PR for '{repo}', expected '{target_repo}'."
        )

    print(f"::notice::Codegen pull request: {pr_url}")


def cmd_summary() -> None:
    env = os.environ
    pr_url = env.get("PR_URL_WAIT", "").strip() or env.get("PR_URL_INITIAL", "").strip()
    if pr_url:
        print(f"::notice::Codegen PR: {pr_url}")
    else:
        print("::notice::Codegen task completed without PR URL.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("prepare-prompt")
    subparsers.add_parser("run-task")
    subparsers.add_parser("wait-task")
    subparsers.add_parser("validate-pr")
    subparsers.add_parser("summary")

    args = parser.parse_args()

    command = args.command
    if command == "prepare-prompt":
        cmd_prepare_prompt()
    elif command == "run-task":
        cmd_run_task()
    elif command == "wait-task":
        cmd_wait_task()
    elif command == "validate-pr":
        cmd_validate_pr()
    elif command == "summary":
        cmd_summary()
    else:  # pragma: no cover - argparse ensures command is valid
        parser.error(f"unknown command: {command}")


if __name__ == "__main__":
    main()
