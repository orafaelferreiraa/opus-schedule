# Opus Schedule - Repository Instructions

## Mission
Maintain and evolve the Azure Functions + Terraform pipeline that automates clip scheduling for LowOpsCast with high reliability, reproducibility, and clear operational diagnostics.

## Project Snapshot
- Runtime: Python 3.13 in Azure Functions.
- IaC: Terraform under infra/terraform.
- CI/CD: .github/workflows/ci-validate.yml (jobs test, terraform-plan) and .github/workflows/deploy.yml (jobs terraform-apply, deploy-function). deploy runs on ci-validate success on main, or manual dispatch.
- Cloud auth in CI: Azure OIDC with azure/login and audience api://AzureADTokenExchange.

## Working Agreement
- Always read current file content before editing.
- Keep patches minimal and focused; avoid unrelated refactors.
- Prefer deterministic commands and explicit error messages.
- For Python changes under src, run targeted pytest for changed behavior.
- For Terraform changes, run fmt, init, validate, and plan semantics locally when possible.

## Commit And Push Policy
- You are authorized to commit and push to GitHub after making requested changes.
- For user-requested fixes, the expected default is commit and push in the same turn after relevant validation succeeds.
- Before commit/push, run relevant validation for the touched scope.
- Use clear conventional messages, for example:
  - ci: ...
  - fix: ...
  - chore: ...
- Never expose secrets in commit messages, logs, or files.

## Safety Rails
- Never commit local-only files such as local.settings.json, .env, virtualenvs, cache folders, or credentials.
- If CI auth fails, keep diagnostics objective and separate auth failure from subscription or RBAC failure.
- For Azure operations, preserve idempotent Terraform behavior and avoid destructive changes unless explicitly requested.
