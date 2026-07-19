---
applyTo: "src/**/*.py,src/tests/**/*.py"
---

# Python Change Standards

- Target Python 3.13 compatibility.
- Keep function-level changes small and testable.
- Prefer explicit error handling and operational logs for Azure Functions paths.
- Preserve behavior of scheduling and curation logic unless the task explicitly changes business rules.

# Validation

- Run dependency install from src when dependency files change.
- Run targeted pytest for touched modules.
- For function entrypoint edits, include test_function_app.py in validation.

# Security

- Never hardcode secrets or tokens.
- Keep local.settings.json and environment files out of commits.
