# Codegen × Agent OS CI
Keep Codegen and Agent OS workflows humming with this reusable GitHub Actions bundle.

## Quickstart
### New repository (first-time seeding)
1. Add Actions secrets: `CODEGEN_ORG_ID`, `CODEGEN_TOKEN`, and one-time `CODEGEN_REPO_ID`.
2. Dispatch the **Seed Agent OS** workflow.
3. Merge the generated PR to add `.agent-os/` and ideally `.codegen/repo-id`.
4. Remove the per-repo `CODEGEN_REPO_ID` secret if `.codegen/repo-id` exists.

### Existing repository
1. Confirm `.agent-os/` is already checked in (or run the seed workflow once).
2. Use the **Spec Push** or **Issue** wrapper workflows for daily runs.

## Required secrets & repo pinning
- `CODEGEN_ORG_ID`: your Codegen organization identifier.
- `CODEGEN_TOKEN`: API token with repo access.

Repo ID resolution order inside the reusable workflow:
1. `secrets.CODEGEN_REPO_ID`
2. `.codegen/repo-id` file (single line)
3. Otherwise: run the seed workflow once with the secret or commit the file.

Never echo secrets or repository IDs in job logs.

## Workflows included
- Reusable core: `.github/workflows/codegen-agents.yml`
- Wrappers:
  - `.github/workflows/seed-agentos.yml` (manual dispatch, `require_agentos=false`)
  - `.github/workflows/codegen-on-push.yml` (runs on `.agent-os/specs/**` or `.specify/specs/**` updates)
  - `.github/workflows/codegen-on-issue.yml` (triggered via the `codegen` label or `/run-codegen` comment)

## How it works
- The SDK call is `Agent(org_id, token).run(prompt)` with repo pinning provided by `CODEGEN_REPO_ID`/`REPOSITORY_ID` environment variables.
- The prompt auto-builder finds the newest spec and supports both Agent OS and Spec Kit layouts.
- PR target validation ensures the generated PR targets `${{ github.repository }}` and fails otherwise.

## Finding your Codegen repo id
```bash
codegen login
codegen repo --list-repos
```
Copy the ID associated with `owner/repo`. Store it once as the `CODEGEN_REPO_ID` secret for seeding, or commit it to `.codegen/repo-id`.

## Troubleshooting
- **401 Unauthorized** → Token/org mismatch or empty secret; regenerate the token and re-paste the secrets.
- **Forked PR** → Secrets are unavailable by design; dispatch the workflow from the main repository.
- **Repo mismatch** → Remote origin differs from target; verify the repo slug guard.
- **“.agent-os not found”** (non-seeding runs) → Seed first with `require_agentos=false`.
- **No PR URL detected** → The agent finished without returning a PR link; inspect the PRs tab manually.
- **Missing repo id** → Add `CODEGEN_REPO_ID` once or commit `.codegen/repo-id`.

## FAQ
- **Can I store secrets at the org level?** Yes; grant access to selected repositories.
- **Do I need `CODEGEN_REPO_ID` forever?** No; rely on `.codegen/repo-id` after seeding.
- **Does `Agent.run()` accept a repo parameter?** No; the repo is injected via environment variables.

## Safety notes
- Never log secrets or repository ID values.
- Workflows use concurrency per repo/ref and request `permissions: contents: read`.

## Appendix: File map
- `.github/workflows/codegen-agents.yml` – reusable workflow invoked by wrappers.
- `.github/workflows/seed-agentos.yml` – seeds Agent OS assets and repo pin file.
- `.github/workflows/codegen-on-push.yml` – listens for spec path pushes.
- `.github/workflows/codegen-on-issue.yml` – converts labeled issues into Codegen runs.
