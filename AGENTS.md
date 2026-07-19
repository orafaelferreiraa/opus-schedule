# Agent Operating Guide

## Scope
This file defines mandatory behavior for AI agents working in this repository.

## Core Rules
- Keep changes minimal and related to the user request.
- Validate touched scope before finalizing work.
- Prefer objective diagnostics with exact failing step names.

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
