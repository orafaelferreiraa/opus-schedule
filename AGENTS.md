# Agent Operating Guide

## Scope
This file defines mandatory behavior for AI agents working in this repository.

## Core Rules
- Keep changes minimal and related to the user request.
- Validate touched scope before finalizing work.
- Prefer objective diagnostics with exact failing step names.

## Project Skills
Project-specific skills live in `.claude/skills/` (Claude Code) and are the source of truth for the
domains below. Load the matching skill before working in that area instead of re-deriving context.

| Skill | Load it when touching |
|---|---|
| `opusclip-api` | any call to api.opus.pro, `src/shared/opus_client.py`, payload/4xx debugging |
| `distribution-strategy` | `schedule_matrix.py`, clip ranking, CTA, cadence, credits — the editorial policy |
| `clip-curation-internals` | `judge.py`, `clip_quality.py`, `library_report.py`, any `JUDGE_*` var, hybrid mode — the mechanics |
| `writing-tests` | new or failing tests in `src/tests/`, adding a telemetry counter, opaque 500 in a handler test |
| `shipping-changes` | validation, commit/push, `ci-validate` → `deploy` chain, red CI, Terraform traps |
| `azure-diagnostics` | production telemetry, App Insights KQL, `lowopscaststate`, storage quota |

Curation is split on purpose: `distribution-strategy` holds *what* to publish and when,
`clip-curation-internals` holds *how* the two LLM paths actually work. A change to the editorial
rubric usually touches both `shared/judge.py` and `shared/clip_quality.py` — see that skill.

## Platform Expertise (plugins, not hand-written)
Azure and Terraform expertise comes from installed plugins declared in `.claude/settings.json`, so
do not re-document it by hand. Plugin skills are namespaced:

| Namespace | Source | Covers |
|---|---|---|
| `/azure:*` | `azure@claude-plugins-official` | Azure diagnostics, App Insights instrumentation, storage, Kusto/KQL, cost, AI/Foundry, RBAC (+ Azure MCP server) |
| `/terraform-skill:*` | `terraform-skill@antonbabenko` | Terraform testing, modules, remote state, CI/CD, security scanning |
| `/azure-agent-skills:*` | `azure-agent-skills@microsoft-agent-skills` | 193 Microsoft Learn skills (azure-functions, azure-monitor, azure-table-storage, …) |

The `.claude/skills/` entries above stay authoritative for **this project's** decisions where they
conflict with generic platform guidance.

## Commit And Push Authorization
- Agents are authorized to commit and push after implementing requested changes.
- When the user asks for a fix in CI/CD or infrastructure, default behavior is to commit and push the relevant files in the same turn after validations pass.
- Stage only relevant files and avoid unrelated modifications.
- Use conventional commit messages and include a short validation summary in the final report.

## Validation Expectations
- Python changes: targeted pytest under src/tests.
- Terraform changes: fmt, init, validate, and plan semantics where possible.
- CI changes: ensure workflow syntax and logical conditions are consistent.

## Security Expectations
- Never commit secrets, credentials, local settings, virtual environments, or cache artifacts.
- Respect repository gitignore and avoid leaking sensitive data in logs.
