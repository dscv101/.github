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
from typing import Any, Dict, Iterable, Mapping, Optional, Tuple


SPEC_PROMPT_PACK = """# Spec-Driven Design Prompt Pack (Domain-Agnostic, EARS-Enhanced, Consistency-First)

## Role
You are a senior systems + product engineer applying a spec-first workflow (in the spirit of Sean Grove's approach).
Transform a Spec into: requirements.md, design.md, tasks.md. The outputs must be domain-agnostic, consistency-first, and ready for reuse across product types (software, hardware, services, processes).

## Hard Limits
- Global character cap (all six files combined): <= 25,000 characters.
- If approaching the cap, apply the Trimming Order (in this order, until within limit):
  1) Reduce narrative prose in design.md (keep bullet lists and IDs intact).
  2) Shorten rationales in requirements.md to one concise clause.
  3) Compress tasks.md descriptions (do not remove Acceptance Criteria or REQ links).
- Never remove: EARS statements, IDs, Verification methods, Traceability references, Acceptance Criteria.

## Consistency Mode = STRICT
- Controlled Vocabulary
  - Use "shall" for normative requirements; avoid "should/may" unless explicitly non-mandatory.
  - Use "system", "component", "interface", "artifact", "operator", "measure".
  - Avoid ambiguous terms: fast, easy, robust, scalable, optimal, user-friendly.
- Grammar & Style
  - Declarative, testable statements. Active voice. No colloquialisms or marketing language.
  - Stable phrasing; avoid synonyms—prefer repeated, consistent terms over variety.
  - Lists use hyphen bullets; one idea per bullet; end each requirement with a period.
- IDs & Traceability
  - Requirements: REQ-001, REQ-002, …
  - Design elements: DES-001, DES-002, …
  - Tasks: TSK-001, TSK-002, …
  - Maintain bidirectional traceability: each DES-### and TSK-### references at least one REQ-###.
- Structure & Ordering
  - Use the exact headers and section order specified below—no extra or missing sections.
- Domain-Agnostic Metrics
  - Prefer neutral, measurable targets (for example throughput/units per time, availability %, MTBF hours, completion time, error rate per operations, accuracy %, resource utilization %, cost per unit).

## Inputs (fill or infer with explicit assumptions)
- Project_Title
- Problem_Statement (1–3 paragraphs)
- Primary_Users & Stakeholders
- Constraints (technical, performance, cost, timeline, operational)
- Non_Functional_Requirements (reliability, maintainability, safety, availability, usability, capacity/throughput, etc.)
- Existing_Assets/Integrations
- Risks/Unknowns

If any field is missing, make minimal reasonable assumptions and list them under Assumptions in requirements.md.

## Output Packaging (exactly 6 blocks, in this order; no text outside these blocks)
BEGIN_FILE: requirements.md
...file content...
END_FILE

BEGIN_FILE: design.md
...file content...
END_FILE

BEGIN_FILE: tasks.md
...file content...
END_FILE

## EARS (Easy Approach to Requirements Syntax)
Write all functional requirements using EARS patterns. For each REQ-###, include Pattern, Statement, Rationale (<= 1 sentence), and Verification (Test | Analysis | Demonstration | Inspection).

Allowed patterns and canonical forms:
1) Ubiquitous: The <system> shall <response>.
2) Event-driven: When <trigger>, the <system> shall <response>.
3) State-driven: While <state>, the <system> shall <response>.
4) Optional feature: Where <feature> is enabled, the <system> shall <response>.
5) Unwanted behavior: If <undesired_trigger>, the <system> shall <mitigation>.

## File Specifications (domain-agnostic)

### 1) requirements.md
Purpose: Source of truth for what the system must do.

Structure (in order):
- Title
- Summary (<= 120 words)
- Assumptions (only those you introduced)
- Stakeholders & Goals
- In-Scope / Out-of-Scope
- Glossary (key terms)
- Functional Requirements (EARS)
  - Group by feature (subheadings).
  - Each entry: REQ-### | Pattern | Statement | Rationale | Verification.
- Non-Functional Requirements (quantified, domain-neutral)
  - Examples of measurable forms: availability >= 99.5%, operator error rate <= 1% per 1,000 ops, process >= 500 units/hour, completion time p95 <= 3 minutes, MTBF >= 1,000 hours.
- Risks & Mitigations
- Traceability Matrix (initial)
  - Columns: REQ-### | DES-### (refs) | TSK-### (refs) | Verification.

Volume: Provide at least 15 functional requirements spanning multiple EARS patterns.

### 2) design.md
Purpose: How the system satisfies the requirements.

Notes: No diagrams in this phase. Provide clear, compact textual descriptions suitable for later diagramming.

Structure (in order):
- Architecture/Approach Overview (one concise paragraph)
- Components (DES-###), Interfaces, and Contracts
  - For each DES-###: Purpose, Related REQ-###, Inputs/Outputs (or Preconditions/Postconditions), Failure Modes, Observability/Telemetry.
- Data/Information Model (entities/artifacts, identifiers/keys, lifecycle, retention)
- Key Flows (happy path + key failure/edge paths; described as numbered steps)
- Non-Functional Design Strategies (capacity, resilience, safety, maintainability, availability, usability)
- Security & Privacy (domain-neutral, minimal but concrete)
- Migration/Rollout/Change Strategy (phased rollout, backfills, feature flags where applicable)
- Updated Traceability Matrix (REQ-### <-> DES-###)

### 3) tasks.md
Purpose: Execution plan.

Structure (in order):
- Milestones (with entry/exit criteria)
- Work Breakdown Structure (epics -> stories -> tasks with TSK-###)
- For each TSK-###: Summary, Owner (role), Inputs, Output/Artifact, Preconditions, Acceptance Criteria (map to REQ-###), Estimate, Dependencies.
- Test/Validation Plan Overview (link verification to tasks)
- Risks/Blockers & Contingencies

## Quality Gates (pre-emit checklist)
- Character cap respected (<= 25,000 across all files).
- Requirements are atomic, testable, EARS-conformant, and domain-agnostic.
- Every DES-### and TSK-### references >= 1 REQ-###.
- No diagrams included; text is clear enough to diagram later.
- No placeholder prose remains.
- NFRs use measurable, neutral metrics.
- Section headers and ordering exactly match this specification.

## Style & Length Targets (for consistency)
- Aim for compact, repeatable phrasing.
- Suggested character budgets (flexible, to help meet the cap):
  - requirements.md <= 15,000
  - design.md <= 15,000
  - tasks.md <= 15,000
- If budgets conflict with coverage, prioritize: (1) correctness, (2) traceability, (3) brevity.

The requirements.md, design.md, and tasks.md must be emitted as separate files in the specs folder. All files need to have clear instructions that are unambiguous. Tasks must be cross linked since they will be turned into issues.
"""


def _write_output_lines(lines: Dict[str, str]) -> None:
    """Append key/value pairs to the GITHUB_OUTPUT file."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        raise SystemExit("::error::GITHUB_OUTPUT environment variable is not set.")
    path = pathlib.Path(output_path)
    with path.open("a", encoding="utf-8") as handle:
        for key, value in lines.items():
            handle.write(f"{key}={value}\n")


def _read_text(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"::error::Failed to read spec '{path}': {exc}") from exc


def _load_sdd_prompt(folder: pathlib.Path) -> str:
    parts: list[str] = []
    for name in ("requirements.md", "design.md", "tasks.md"):
        doc = folder / name
        if doc.exists():
            parts.append(_read_text(doc))
    if not parts:
        raise SystemExit(
            f"::error::SDD spec folder '{folder.as_posix()}' is missing requirements/design/tasks docs."
        )
    joined = "\n\n".join(parts)
    header = f"Follow the latest SDD specification at {folder.as_posix()}"
    return f"{header}\n\n{joined}"


def _load_spec_prompt(folder: pathlib.Path, spec_path: pathlib.Path) -> str:
    spec_text = _read_text(spec_path).strip()
    context_lines = [
        SPEC_PROMPT_PACK.strip(),
        "",
        "## Spec Context",
        f"- Spec folder: {folder.as_posix()}",
        f"- Spec file: {spec_path.as_posix()}",
        "",
        "## Spec Content",
        spec_text,
    ]
    return "\n".join(context_lines)


def _newest_path(paths: Iterable[pathlib.Path]) -> Optional[pathlib.Path]:
    newest: Optional[pathlib.Path] = None
    newest_mtime = -1.0
    for path in paths:
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            continue
        if mtime > newest_mtime:
            newest_mtime = mtime
            newest = path
    return newest


def _discover_latest_sdd_spec(root: pathlib.Path) -> Optional[pathlib.Path]:
    if not root.exists():
        return None
    if not root.is_dir():
        return None
    candidates: list[pathlib.Path] = []
    for child in root.iterdir():
        if child.is_dir():
            requirements = child / "requirements.md"
            design = child / "design.md"
            tasks = child / "tasks.md"
            if requirements.exists() or design.exists() or tasks.exists():
                candidates.append(child)
    if not candidates:
        return None
    return _newest_path(candidates)


def _discover_latest_spec_folder(root: pathlib.Path) -> Optional[pathlib.Path]:
    if not root.exists():
        return None
    if not root.is_dir():
        return None
    candidates: list[pathlib.Path] = []
    for child in root.iterdir():
        if not child.is_dir():
            continue
        spec = child / "spec.md"
        if spec.exists():
            candidates.append(child)
    if not candidates:
        return None
    return _newest_path(candidates)


def _legacy_window_active(env: Mapping[str, str]) -> bool:
    flag = env.get("LEGACY_DISCOVERY", "").strip().lower()
    return flag not in {"", "0", "false"}


def _build_prompt_from_candidate(candidate: pathlib.Path) -> Tuple[str, str]:
    if candidate.is_dir():
        requirements = candidate / "requirements.md"
        design = candidate / "design.md"
        tasks = candidate / "tasks.md"
        spec = candidate / "spec.md"
        if requirements.exists() or design.exists() or tasks.exists():
            prompt = _load_sdd_prompt(candidate)
            print(f"::notice::Using SDD spec '{candidate.as_posix()}' for prompt generation.")
            return prompt, "sdd"
        if spec.exists():
            prompt = _load_spec_prompt(candidate, spec)
            print(
                "::notice::Using Spec-Driven Design prompt pack for "
                f"'{spec.as_posix()}' to generate SDD artifacts."
            )
            return prompt, "spec-pack"
        raise SystemExit(
            f"::error::Spec folder '{candidate.as_posix()}' missing SDD docs and spec.md."
        )
    if candidate.is_file() and candidate.name.lower() == "spec.md":
        prompt = _load_spec_prompt(candidate.parent, candidate)
        print(
            "::notice::Using Spec-Driven Design prompt pack for "
            f"'{candidate.as_posix()}' to generate SDD artifacts."
        )
        return prompt, "spec-pack"
    prompt = f"Follow the latest specification at {candidate.as_posix()}\n\n" + _read_text(candidate)
    normalized = candidate.as_posix()
    if any(part in normalized for part in (".agent-os/", ".specify/")):
        print(f"::warning::Selected legacy spec '{normalized}'; migrate to SDD soon.")
        return prompt, "legacy"
    print(f"::notice::Using spec '{normalized}' for prompt generation.")
    return prompt, "spec"


def cmd_prepare_prompt() -> None:
    env = os.environ

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

        if candidate is None:
            custom_glob = env.get("INPUT_SPECS_GLOB", "").strip()
            matches: list[pathlib.Path] = []
            if custom_glob:
                matches.extend(pathlib.Path(match) for match in glob.glob(custom_glob, recursive=True))
                custom_candidate = _newest_path(p for p in matches if p.exists())
                if custom_candidate is not None:
                    candidate = custom_candidate

            if candidate is None:
                sdd_candidate = _discover_latest_sdd_spec(pathlib.Path(".sdd/specs"))
                if sdd_candidate is not None:
                    candidate = sdd_candidate

            if candidate is None:
                spec_folder = _discover_latest_spec_folder(pathlib.Path(".sdd/specs"))
                if spec_folder is not None:
                    candidate = spec_folder

            if candidate is None:
                if _legacy_window_active(env):
                    legacy_globs = [".agent-os/specs/**/*", ".specify/specs/**/*"]
                    legacy_candidates = [pathlib.Path(match) for pattern in legacy_globs for match in glob.glob(pattern, recursive=True)]
                    legacy_newest = _newest_path(p for p in legacy_candidates if p.is_file())
                    if legacy_newest is not None:
                        candidate = legacy_newest
                else:
                    print("::notice::Legacy discovery disabled; SDD specs are required.")

        if candidate is not None:
            prompt, source = _build_prompt_from_candidate(candidate)
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
        repo_id = int(resolved_repo_id)
    except ValueError as exc:
        raise SystemExit("::error::Resolved repository id must be an integer.") from exc

    try:
        from codegen import Agent  # type: ignore import-not-found
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"::error::Failed to import Codegen Agent: {exc}") from exc

    try:
        from codegen_api_client.models.create_agent_run_input import CreateAgentRunInput  # type: ignore import-not-found
        from codegen.agents.agent import AgentTask  # type: ignore import-not-found
    except Exception:
        CreateAgentRunInput = None  # type: ignore[assignment]
        AgentTask = None  # type: ignore[assignment]

    agent = Agent(org_id=env["CODEGEN_ORG_ID"], token=env["CODEGEN_TOKEN"])
    prompt = env.get("PROMPT", "")

    result: Any
    if CreateAgentRunInput is not None and AgentTask is not None:
        try:
            run_input = CreateAgentRunInput(prompt=prompt, repo_id=repo_id)
            agent_run_response = agent.agents_api.create_agent_run_v1_organizations_org_id_agent_run_post(  # type: ignore[attr-defined]
                org_id=int(agent.org_id),
                create_agent_run_input=run_input,
                authorization=f"Bearer {agent.token}",
                _headers={"Content-Type": "application/json"},
            )
            result = AgentTask(agent_run_response, agent.api_client, agent.org_id)
        except TypeError:
            # Older SDKs may not accept repo_id; fall back to the default behaviour.
            try:
                result = agent.run(prompt=prompt)
            except Exception as exc:  # noqa: BLE001
                message = str(exc)
                if "401" in message or "Unauthorized" in message:
                    print(
                        "::error::Unauthorized: verify CODEGEN_ORG_ID/CODEGEN_TOKEN secrets and repository permissions."
                    )
                raise
        except Exception as exc:  # noqa: BLE001
            message = str(exc)
            if "401" in message or "Unauthorized" in message:
                print(
                    "::error::Unauthorized: verify CODEGEN_ORG_ID/CODEGEN_TOKEN secrets and repository permissions."
                )
            raise
    else:
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
