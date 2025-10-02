#!/usr/bin/env python3
"""Migrate legacy AgentOS specs into Spec-Driven Design (SDD) folders."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Mapping, Tuple

LEGACY_TO_SDD: Mapping[str, str] = {
    "spec.md": "requirements.md",
    "requirements.md": "requirements.md",
    "specification.md": "requirements.md",
    "technical-spec.md": "design.md",
    "design.md": "design.md",
    "architecture.md": "design.md",
    "tasks.md": "tasks.md",
    "todo.md": "tasks.md",
    "workplan.md": "tasks.md",
}

DEFAULT_PLACEHOLDER: Mapping[str, str] = {
    "requirements.md": "# Requirements\n\n<!-- TODO: migrate legacy requirements content -->\n",
    "design.md": "# Design\n\n<!-- TODO: migrate legacy design content -->\n",
    "tasks.md": "# Tasks\n\n<!-- TODO: migrate legacy tasks content -->\n",
}


@dataclass
class MigrationResult:
    src_folder: Path
    dest_folder: Path
    written: List[Path]
    skipped: List[Tuple[Path, str]]
    warnings: List[str]


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def discover_specs(src_root: Path) -> List[Path]:
    if not src_root.exists():
        return []
    return sorted([p for p in src_root.iterdir() if p.is_dir()])


def collect_payload(src_folder: Path) -> Tuple[Dict[str, str], List[str]]:
    payload: Dict[str, str] = {}
    warnings: List[str] = []
    for legacy_path in src_folder.glob("**/*.md"):
        relative_name = legacy_path.name.lower()
        bucket = LEGACY_TO_SDD.get(relative_name)
        content = legacy_path.read_text(encoding="utf-8")
        if bucket:
            payload[bucket] = content
        else:
            warnings.append(f"Unmapped file: {legacy_path.relative_to(src_folder)}")
    return payload, warnings


def write_sdd(destination: Path, payload: Mapping[str, str], dry_run: bool) -> List[Path]:
    written: List[Path] = []
    destination.mkdir(parents=True, exist_ok=True)
    for filename in ("requirements.md", "design.md", "tasks.md"):
        target = destination / filename
        content = payload.get(filename, DEFAULT_PLACEHOLDER[filename])
        if target.exists():
            existing = target.read_text(encoding="utf-8")
            if _sha256_text(existing) == _sha256_text(content):
                continue
        if dry_run:
            written.append(target)
        else:
            target.write_text(content, encoding="utf-8")
            written.append(target)
    return written


def migrate_folder(src_folder: Path, dest_root: Path, dry_run: bool) -> MigrationResult:
    payload, warnings = collect_payload(src_folder)
    dest_folder = dest_root / src_folder.name
    written = write_sdd(dest_folder, payload, dry_run)
    skipped: List[Tuple[Path, str]] = []
    if dry_run:
        skipped = [(p, "dry-run") for p in written]
        written = []
    return MigrationResult(src_folder, dest_folder, written, skipped, warnings)


def parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, default=Path(".agent-os/specs"), help="Legacy spec root")
    parser.add_argument("--dest", type=Path, default=Path(".sdd/specs"), help="SDD spec root")
    parser.add_argument("--dry-run", action="store_true", help="Log planned writes without touching disk")
    parser.add_argument(
        "--since",
        type=str,
        default="",
        help="Only migrate folders on or after this date (YYYY-MM-DD).",
    )
    return parser.parse_args(argv)


def filter_since(folders: List[Path], since: str) -> List[Path]:
    if not since:
        return folders
    try:
        threshold = dt.datetime.strptime(since, "%Y-%m-%d").date()
    except ValueError as exc:
        raise SystemExit(f"Invalid --since value: {since}") from exc
    result: List[Path] = []
    for folder in folders:
        prefix = folder.name.split("-", 1)[0]
        try:
            folder_date = dt.datetime.strptime(prefix, "%Y%m%d").date()
        except ValueError:
            try:
                folder_date = dt.datetime.strptime(prefix, "%Y-%m-%d").date()
            except ValueError:
                result.append(folder)
                continue
        if folder_date >= threshold:
            result.append(folder)
    return result


def main(argv: List[str]) -> int:
    args = parse_args(argv)
    src_root: Path = args.src
    dest_root: Path = args.dest
    dry_run: bool = args.dry_run

    folders = filter_since(discover_specs(src_root), args.since)
    if not folders:
        print(f"No AgentOS specs found in {src_root}.")
        return 0

    outcomes: List[MigrationResult] = []
    for folder in folders:
        result = migrate_folder(folder, dest_root, dry_run)
        outcomes.append(result)
        action = "Would write" if dry_run else "Migrated"
        print(f"{action} {folder} -> {result.dest_folder}")
        for warning in result.warnings:
            print(f"::warning::{folder.name}: {warning}")
        if dry_run:
            for target, reason in result.skipped:
                print(f"   - {target} ({reason})")
        else:
            for target in result.written:
                print(f"   - wrote {target}")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
