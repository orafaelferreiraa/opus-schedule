# Opus Schedule - Repository Instructions

## Mission
Maintain and evolve the **local** clip-curation and scheduling toolchain for LowOpsCast: prepare
clips from OpusClip, curate content by hand, and schedule posts via the OpusClip REST API.
Reliability and reproducibility on a developer machine — no cloud infrastructure.

## Project Snapshot
- Runtime: Python 3.12+ run locally (`tools/curate/` on top of `src/shared/`).
- Distribution: OpusClip REST API (`api.opus.pro`) — the external service that actually publishes.
- No Azure, no Terraform, no CI/CD — the cloud stack was decommissioned on 2026-09-05 (see README §8).

## Working Agreement
- Always read current file content before editing.
- Keep patches minimal and focused; avoid unrelated refactors.
- For Python changes under `src`, run targeted pytest: `cd src && PYTHONPATH=. python -m pytest -q tests/`.

## Commit And Push Policy
- Commit and push **only when the user asks**.
- Use clear conventional messages (fix:, chore:, feat:, …).
- Never expose secrets in commit messages, logs, or files.

## Safety Rails
- Never commit local-only files such as `.env`, virtualenvs, cache folders, or credentials.
- `OPUSCLIP_API_KEY` lives in the local environment.
