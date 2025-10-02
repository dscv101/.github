# Codegen × Spec-Driven Design (SDD) CI

This guide walks through managing Codegen runs with the new Spec-Driven Design (SDD) layout. All automation now consumes specs under `.sdd/specs/**` and falls back to legacy AgentOS/Specify content only during a short deprecation window.

## 1. Prerequisites
- GitHub Actions secrets: `CODEGEN_ORG_ID`, `CODEGEN_TOKEN`, optionally `CODEGEN_REPO_ID`.
- Codegen repo pin in `.codegen/repo-id` or the `CODEGEN_REPO_ID` secret.

## 2. Authoring Specs
1. Copy the templates in `.sdd/templates/` into a new folder named `<YYYY-MM-DD>-<spec-name>/` under `.sdd/specs/`.
2. Fill in:
   - `requirements.md` — context, functional and non-functional requirements, success criteria.
   - `design.md` — architecture diagrams/notes, component responsibilities, data flows.
   - `tasks.md` — work breakdown, machine actions, validation checklist.
3. Commit the folder; pushing to the branch triggers the Codegen workflow automatically.

## 3. Running Codegen
- **Spec Push (`Codegen on Spec Push`)**
  - Fires on any push that touches `.sdd/specs/**` on the default branch or tracked branches.
  - Uses the newest SDD spec by default; legacy specs are ignored once the deprecation window expires.

- **Issue Trigger (`Codegen on Issues`)**
  - Label an issue with `codegen` or comment `/run-codegen`.
  - Optionally include `spec_path: .sdd/specs/<...>/requirements.md` or embed a ```prompt``` block to override the auto-selected spec.

- **Manual Dispatch**
  - From the Actions tab, run the `Codegen on Spec Push` workflow using `workflow_dispatch` inputs to override prompt/spec path or disable waiting.

All routes call the shared reusable workflow `.github/workflows/codegen-agents.yml`, which prioritizes SDD folders and still invokes `Agent(<ORG_ID>, <TOKEN>).run(prompt)`.

## 4. Migrating Legacy Specs
1. Inspect existing AgentOS specs under `.agent-os/specs/`.
2. Run the helper in dry-run mode to preview conversions:
   ```bash
   python scripts/migrate_agentos_to_sdd.py --dry-run
   ```
3. Re-run without `--dry-run` once satisfied; review new SDD files and commit them.
4. Delete the migrated `.agent-os/` folders after verifying the new layout.

## 5. Monitoring & Deprecation
- The reusable workflow emits `::warning::` logs when it falls back to legacy specs; treat these as prompts to finish migration.
- After `<DEPRECATION_DAYS>` (defaults to 14), disable `LEGACY_DISCOVERY` in the workflow environment to stop legacy discovery entirely.
- Confirm that deleting `.agent-os/**` no longer blocks CI—the guard has been removed.

## 6. Troubleshooting
- **No spec detected** → Ensure `.sdd/specs/` exists with at least one folder and all three docs; otherwise the workflow posts a fallback notice.
- **Wrong spec selected** → Provide `spec_path` via dispatch input or issue body to target a specific SDD folder.
- **Missing repo id** → Add `CODEGEN_REPO_ID` secret or commit `.codegen/repo-id`.
- **Auth errors** → Rotate `CODEGEN_TOKEN` and confirm the secret is populated.

For additional context, see the top-level `README.md` or the comments inside `.github/scripts/codegen_workflow.py`.
