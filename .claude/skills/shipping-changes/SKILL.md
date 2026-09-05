---
name: shipping-changes
description: Fluxo de validação, commit e push local deste repo (pytest). Use ao terminar qualquer mudança em src/ ou tools/, e quando o usuário pedir para validar, commitar ou subir.
---

# Validar e subir mudanças

Projeto **100% local** desde 2026-09-05 — sem Terraform, sem Azure, sem CI/CD (workflows removidos).
Commitar e dar push **só quando o usuário pedir explicitamente** (ver `AGENTS.md`).

## Checklist

```
- [ ] 1. Validar o escopo tocado (pytest)
- [ ] 2. Stage só dos arquivos relevantes
- [ ] 3. Commit convencional (só se o usuário pediu)
- [ ] 4. Push (só se o usuário pediu)
- [ ] 5. Reportar o que rodou e passou
```

## Passo 1 — Validar

Pytest roda da **raiz** do repo (`pyproject.toml` já injeta `src/` no `sys.path` e aponta
`testpaths` para `src/tests`):

```bash
pytest -q                            # suíte completa (rápida, ~30 testes)
pytest src/tests/test_x.py -q        # alvo
```

Ambiente ainda não montado (`ModuleNotFoundError: pytest`):

```bash
python3 -m venv .venv && .venv/bin/pip install -r src/requirements.txt pytest
.venv/bin/python -m pytest -q
```

Mexeu em `src/requirements.txt`? Reinstale antes de rodar.

Mexeu em `tools/curate/*.py`? Não há suíte dedicada — rode o script em dry-run contra um
`--project-id` conhecido como smoke test (ver `clip-curation-internals`).

## Passo 2-4 — Commit e push

Stage cirúrgico. **Nunca** commitar: `src/local.settings.json` (se recriado), `.venv/`,
`__pycache__/`, `.pytest_cache/`, `.env`, `review/**/clips.json` e `transcripts.md` (gitignored,
volumosos e regeneráveis).

Mensagem convencional (`feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`), imperativa, escopo
quando ajudar: `fix(judge): ...`, `feat(curate): ...`.

## Passo 5 — Reportar

O que rodou e passou (contagem de testes), o que ficou de fora da validação (dizer explicitamente
em vez de omitir), e o hash do commit se houve push.
