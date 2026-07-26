---
name: shipping-changes
description: Fluxo de validação, commit, push e acompanhamento do pipeline deste repo (pytest + terraform fmt/init/validate/plan, cadeia ci-validate → deploy, func publish em Flex Consumption). Use ao terminar qualquer mudança em src/, infra/terraform/ ou .github/workflows/, ao investigar CI vermelho ou deploy falhado, e quando o usuário pedir para validar, commitar, subir, deployar, ou perguntar por que o pipeline quebrou.
---

# Validar e subir mudanças

Este repo autoriza o agente a **commitar e dar push** após implementar o que foi pedido (ver
`AGENTS.md`). Padrão: validar → stage só do escopo → commit convencional → push → acompanhar CI.

## Checklist

```
- [ ] 1. Validar o escopo tocado (comandos abaixo)
- [ ] 2. Stage só dos arquivos relevantes
- [ ] 3. Commit convencional
- [ ] 4. Push na branch ativa
- [ ] 5. Acompanhar ci-validate → deploy
- [ ] 6. Reportar hash + o que foi validado
```

## Passo 1 — Validar por escopo

**Python (`src/`)** — pytest roda da **raiz** do repo (`pyproject.toml` já injeta `src/` no
`sys.path` e aponta `testpaths` para `src/tests`):

```bash
pytest -q                            # suíte completa (rápida)
pytest src/tests/test_x.py -q        # alvo
```

Ambiente ainda não montado (`ModuleNotFoundError: pytest` ou `azure.functions`):

```bash
python3 -m venv .venv && .venv/bin/pip install -r src/requirements.txt pytest
.venv/bin/python -m pytest -q
```

Mexeu em `function_app.py`? Inclua **sempre** `src/tests/test_function_app.py`.
Mexeu em `src/requirements.txt`? Reinstale antes de rodar.

**Terraform (`infra/terraform/`)** — o CI roda `fmt -check -recursive`, então formate:

```bash
cd infra/terraform
terraform fmt -recursive
terraform init      # backend azurerm remoto; requer az login com acesso ao data plane de blob
terraform validate
terraform plan      # só se houver credencial Azure local; senão delegue ao CI
```

Sem credencial local, diga isso explicitamente e deixe o `plan` para o `ci-validate`.

**Workflows (`.github/workflows/`)** — não há validador local; revise sintaxe YAML e a **lógica
das condições** `if:` (é onde os bugs moram neste repo, ver abaixo).

## Passo 2-4 — Commit e push

Stage cirúrgico. **Nunca** commitar: `src/local.settings.json`, `.venv/`, `__pycache__/`,
`.pytest_cache/`, `*.tfstate*`, `infra/ci-artifacts/`, `.env`.

Mensagem convencional (`feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `ci:`, `docs:`), imperativa,
escopo quando ajudar: `fix(ci): ...`, `feat(judge): ...`.

## Passo 5 — Acompanhar o pipeline

A cadeia é **duas workflows encadeadas** — `deploy` **não** dispara em push:

```
push/PR em main → ci-validate (test + terraform plan)
                      └── on: workflow_run [completed] + conclusion == success + head_branch == main
                          → deploy (terraform-apply → deploy-function)
```

```bash
gh run list --limit 5
gh run watch <run-id>                 # acompanha ao vivo
gh run view <run-id> --log-failed     # só os passos que falharam
gh run view <run-id> --job <job-id> --log
```

Depois do `ci-validate` verde em `main`, **espere o `deploy` aparecer** — se não aparecer, a
condição `if:` do `terraform-apply` reprovou (branch != main, ou conclusion != success).

`deploy` também aceita `workflow_dispatch` em `main` (`gh workflow run deploy.yml --ref main`).

## Modos de falha conhecidos

| Sintoma | Causa real | Correção |
|---|---|---|
| `terraform init` falha no backend (403 no blob) | O SP do CI precisa de **Storage Blob Data Contributor** em `stoopusstate` — o backend `azurerm` usa Azure AD, e `Owner` **não** cobre o data plane de blob | atribuir a role no storage account |
| `fmt -check` vermelho | esqueceu `terraform fmt -recursive` | rodar e recommitar |
| "Azure authentication failed" | OIDC não configurado **e** `AZURE_CREDENTIALS` ausente | o workflow tem OIDC com fallback para SP secret; configurar um dos dois |
| "landed in the wrong subscription context" | `AZURE_SUBSCRIPTION_ID` divergente do login | alinhar o secret |
| `terraform output did not produce function_app_name` | `terraform-apply` não aplicou de fato | ver o log do job anterior, não o do publish |
| `func azure functionapp publish` falha | pacote/deps; o log fica no artifact `function-publish.log` | baixar o artifact do run |
| App Service Plan: "Flex é 1 app por plano" | tentativa de reusar o plano do jobfinder | FC1 exige plano dedicado — já é o desenho atual |

Artifacts de diagnóstico (plan, publish log) são anexados ao run com `if: always()` —
`gh run download <run-id>` antes de teorizar.

### Duas armadilhas que parecem bug e não são

**1. O `plan` do `ci-validate` sempre mostra diff em `app_settings` — e aplicar dali apaga a chave.**

`ci-validate.yml` **não define nenhum `TF_VAR_*`**; `deploy.yml:43-47` define quatro
(`opusclip_api_key`, `opusclip_org_id`, `notification_email_to`, `notification_email_from`). Como
`opusclip_api_key` tem default `""` (`variables.tf`), o plan do `ci-validate` roda com a chave vazia
e sempre propõe um update in-place de `app_settings` **zerando o segredo em produção**.

Ou seja: o plan do `ci-validate` **não é** estruturalmente o plan que o `deploy` aplica. É esperado.
Nunca rodar `apply` a partir do contexto do `ci-validate`, e não "consertar" esse diff no Terraform.

**2. `app_service_plan_sku = "B1"` não é um fallback funcional, apesar do que a variável promete.**

A `description` em `variables.tf:19-28` anuncia `B1` como "fallback confiável se faltar quota FC1", e
a mensagem de validação sugere `FC1, B1, EP1`. Mas `main.tf:68` é
`azurerm_function_app_flex_consumption`, que **exige** plano Flex. Trocar a variável para `B1` cria um
plano B1 e faz o recurso do Function App falhar no apply, com erro confuso. Os dois workflows
plumbam o SKU como variável (`ci-validate.yml:130-136`, `deploy.yml:112-118`), o que reforça a
ilusão de que é um switch suportado.

Sair de FC1 de verdade exige **trocar o tipo do recurso** para `azurerm_linux_function_app` com
`site_config`/storage próprios — não é mudança de variável. Se o pedido for "não temos quota FC1,
usa B1", explicar isso antes de mexer.

## Passo 6 — Reportar

Hash do commit, o que rodou e passou, e o estado do CI. Se algo não foi validado (ex.: `plan` sem
credencial local), dizer explicitamente em vez de omitir.
