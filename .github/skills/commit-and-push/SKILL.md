# Commit And Push Skill

## Purpose
Standardize the post-change flow so code changes are validated, committed, and pushed consistently.

## Use This Skill When
- The user asks for a fix, enhancement, refactor, or CI change that modifies repository files.
- The change set is ready and validation has been run for touched areas.
- The repository branch is intended to receive direct pushes.

## Authorization
- This repository grants agent authorization to perform commit and push after requested changes.

## Required Steps
1. Review changed files and ensure scope matches the user request.
2. Run relevant checks:
   - Python scope: install dependencies if needed and run targeted pytest.
   - Terraform scope: fmt, init, validate, and plan semantics where possible.
   - CI scope: verify workflow syntax and logic.
3. Stage only relevant files.
4. Create a conventional commit message with clear intent.
5. Push to the active branch.
6. Report commit hash and what was validated.

## Guardrails
- Do not commit secrets, env files, local caches, or generated local artifacts.
- Do not use destructive git history operations unless explicitly requested.
- If terminal environment is unstable, report limitation and provide exact fallback commands.
