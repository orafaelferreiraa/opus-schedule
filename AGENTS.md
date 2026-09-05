# Agent Operating Guide

## Scope
This file defines mandatory behavior for AI agents working in this repository.

## Project reality (as of 2026-09-05)
LowOpsCast runs **100% locally**. There is no Azure infrastructure, no Function App, and no
CI/CD pipeline anymore — all decommissioned (see README §8). The workflow is: prepare clips →
**human content curation** → plan (dry-run) → schedule via the OpusClip API, all driven from
`tools/curate/` on top of the `src/shared/` library. OpusClip (`api.opus.pro`) is the external
service that actually publishes.

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
| `clip-curation-internals` | `judge.py`, `clip_quality.py`, `library_report.py`, the `tools/curate/` harness, the curation rubric |
| `writing-tests` | new or failing tests in `src/tests/` |
| `shipping-changes` | local validation and commit/push flow |

Curation is split on purpose: `distribution-strategy` holds *what* to publish and when;
`clip-curation-internals` holds *how* the mechanical gate and the local curation harness work.

> **Stale skills:** parts of `shipping-changes` and `azure-diagnostics` still describe the old
> Azure/CI/Terraform pipeline and the LLM Judge/Foundry — both gone. Trust the code and README
> over those descriptions until the skills are updated.

## Validation Expectations
- Python changes: `cd src && PYTHONPATH=. python -m pytest -q tests/` (targeted where possible).

## Commit And Push
- Commit and push **only when the user asks** — do not commit/push automatically.
- Stage only relevant files; avoid unrelated modifications.
- Use conventional commit messages and include a short validation summary in the final report.

## Security Expectations
- Never commit secrets, credentials, local settings, virtual environments, or cache artifacts.
- `OPUSCLIP_API_KEY` lives in the local environment, never in the repo.
