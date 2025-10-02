# .github

This repository centralizes reusable Codegen automation shared across projects.

## Spec-Driven Design (SDD)

Specs now live under `.sdd/specs/<YYYY-MM-DD>-<name>/` with three canonical documents:

- `requirements.md` — product context, functional and non-functional requirements.
- `design.md` — architecture, data flows, and implementation notes.
- `tasks.md` — work breakdown, machine actions, and validation steps.

If a spec folder only contains `spec.md`, the Codegen push workflow now packages that document with the Spec-Driven Design prompt pack and asks Codegen to generate the three canonical files automatically.

Copy the templates in `.sdd/templates/` when authoring new specs or run the migration script in `scripts/migrate_agentos_to_sdd.py` to convert legacy AgentOS specs.

## Manual Project Bootstrap

- Trigger the `Manual Project Bootstrap` workflow from the Actions tab to instantiate a Project V2 Kanban board, milestone, epic, and task skeletons.
- Supply a project title, optional description, and a JSON payload that follows the shape `{"milestones": [{"title": ..., "epics": [{"title": ..., "tasks": [{"title": ...}]}]}]}`.
- The workflow uses the Codegen API to run `scripts/create_project_structure.py`, creating the project, adding milestones via REST, and linking epics/tasks into the board with `Status` defaulted to `To do`.
- Provide an access token with Projects/Issues write permissions by either (a) creating a classic PAT with `repo`, `project` scopes (or a fine-grained token with equivalent access) and storing it as the `MANUAL_PROJECT_TOKEN` repository secret, or (b) ensuring the default `GITHUB_TOKEN` has read/write workflow permissions plus project access in **Settings ▸ Actions ▸ General**.
- Each epic body is rewritten with a checklist of the generated child issues so GitHub recognises the parent/child hierarchy of work items.
