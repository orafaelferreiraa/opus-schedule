# Configuração da curadoria — matriz completa

## Conteúdo

- Matriz de env vars (default por arquivo × Terraform × sobrescrevível no body)
- Campos aceitos no corpo do POST
- Os dois contratos JSON, lado a lado
- Cadeia de precedência
- Autenticação

## Matriz de env vars

Coluna **body?** = pode ser sobrescrito no corpo do `POST /schedule-existing-clips`.
`—` = o arquivo não lê essa variável.

| Env var | Default `judge.py` | Default `clip_quality.py` | Terraform (`main.tf`) | body? |
|---|---|---|---|---|
| `JUDGE_MODE` | `off` | — | `rules_only` | ✅ `judge_mode` |
| `JUDGE_THRESHOLD` | `70` | — | `70` | ✅ `judge_threshold` |
| `JUDGE_INCLUDE_REVIEW_IN_DRY_RUN` | — | — | `true` | ✅ |
| `JUDGE_MODEL_DEPLOYMENT_PRIMARY` | `gpt-5-mini` | `gpt-5-mini` | `var.judge_primary_model` | ✅ |
| `JUDGE_MODEL_DEPLOYMENT_FALLBACK` | `gpt-5-mini` | — | `var.judge_fallback_model` | ✅ |
| `JUDGE_AZURE_OPENAI_ENDPOINT` | `""` | `""` | endpoint do Foundry compartilhado | ❌ |
| `JUDGE_AZURE_OPENAI_API_KEY` | `""` | `""` | (secret) | ❌ |
| `JUDGE_AUTH_MODE` | **`api_key`** | **`managed_identity`** | `var.judge_auth_mode` | ❌ |
| `JUDGE_API_VERSION` | **`2025-01-01-preview`** | **`2024-12-01-preview`** | `2024-12-01-preview` | ❌ |
| `JUDGE_TIMEOUT_MS` | **`12000`** | **`30000`** | `12000` | ❌ |
| `JUDGE_MAX_RETRIES` | `2` | — | `2` | ❌ |
| `JUDGE_MIN_DURATION_MS` | `10000` | — | **não setado** | ❌ |
| `JUDGE_MAX_DURATION_MS` | `180000` | — | **não setado** | ❌ |
| `JUDGE_MIN_TEXT_CHARS` | `10` | — | **não setado** | ❌ |
| `JUDGE_MAX_COMPLETION_TOKENS` | **não lido** | `1500` | **não setado** | ❌ |
| `JUDGE_PROVIDER` | `foundry` (**morto**) | — | `foundry` | ❌ |

### Como ler esta matriz

**Em produção**, o Terraform harmoniza o que diverge por default: `auth_mode`, `api_version`,
`timeout_ms`, `threshold` e os deployments recebem o **mesmo** valor nos dois arquivos. As colunas de
default divergentes mordem em **execução local, em testes, e se alguém remover a linha do
`main.tf`** — não no ambiente deployado.

O que o Terraform **não** consegue harmonizar, porque é divergência de código e não de config:

- `max_tokens: 300` hardcoded em `judge.py:248` versus `max_completion_tokens` em
  `clip_quality.py:169`. Nomes de parâmetro diferentes na requisição.
- Política de duração: 10–180 s (`judge.py`) versus 20–90 s (`DEFAULT_RULES` em `clip_quality.py`).
- Contrato JSON de saída (abaixo).
- Serial versus `ThreadPoolExecutor(max_workers=10)`.

As três variáveis **não setadas** pelo Terraform (`JUDGE_MIN_DURATION_MS`, `JUDGE_MAX_DURATION_MS`,
`JUDGE_MIN_TEXT_CHARS`) caem no default do código em produção. `JUDGE_MAX_COMPLETION_TOKENS` também
— e no caminho de agendamento não é lido de todo lugar.

## Campos aceitos no corpo do POST

`/schedule-existing-clips` — `judge.py:38-70` só lê estes cinco do body:

```json
{
  "judge_mode": "rules_only",
  "judge_threshold": 70,
  "judge_include_review_in_dry_run": true,
  "judge_model_deployment_primary": "gpt-5-mini",
  "judge_model_deployment_fallback": "gpt-5-mini"
}
```

Todo o resto é **env-only**. Passar `auth_mode`, `api_version`, `timeout_ms`, `max_retries`,
`min_duration_ms`, `max_duration_ms` ou `min_text_chars` no body é **silenciosamente ignorado** — não
gera erro de validação.

`/analyze-library` não expõe `max_workers`; a concorrência de 10 é fixa em `library_report.py:100`.

## Os dois contratos JSON

### `judge.py` — `_safe_json` (`:301-307`)

Só estas três chaves são extraídas; qualquer outra que o modelo devolva é descartada.

```json
{
  "final_score": 0,
  "soft_signals": { "payoff": 0, "clareza": 0, "contexto": 0, "engajamento": 0, "polimento": 0 },
  "audit_reason": "frase curta em PT-BR"
}
```

`final_score` é clampeado em 0–100 (`judge.py:184`). `soft_signals` só sobrevive se for um dict.
A decisão `APPROVE`/`REVIEW`/`REJECT` é **derivada** do score, não vem do modelo.

### `clip_quality.py` — `_LLM_SYSTEM` (`:118-123`)

```json
{
  "final_score": 0,
  "approve": false,
  "content_flags": ["sem_payoff", "generico", "anedota_fraca", "fora_do_tema",
                    "previsivel", "sem_insight", "gancho_fraco", "incompleto"],
  "speech_flags": ["repeticao", "pausas", "filler", "gaguejo"],
  "reason": "frase curta em PT-BR"
}
```

Aqui o modelo devolve `approve` **diretamente** — não há derivação por threshold. É a diferença
estrutural entre os dois caminhos: um decide por faixa de score, o outro delega a decisão ao modelo.

## Cadeia de precedência

Caminho de agendamento, para os cinco campos sobrescrevíveis:

```
corpo do POST  →  env var (app setting via Terraform)  →  default no código
```

Para todos os outros:

```
env var (app setting via Terraform)  →  default no código
```

## Autenticação

Os dois arquivos suportam os mesmos dois modos, com defaults opostos.

**`api_key`** — header `api-key: <JUDGE_AZURE_OPENAI_API_KEY>`. Levanta
`RuntimeError` se a chave estiver ausente (`judge.py:321-322`, `clip_quality.py:143-144`).

**`managed_identity`** — `DefaultAzureCredential(exclude_interactive_browser_credential=True)` +
`get_bearer_token_provider`, header `Authorization: Bearer <token>` (`judge.py:311-318`). Exige o
role assignment na conta do Foundry — que é criado por
`azurerm_role_assignment.function_foundry` (`main.tf:131-135`), com escopo em um recurso de **outro**
resource group (`rg-jsearch`).

URL montada nos dois casos:

```
{endpoint}/openai/deployments/{deployment}/chat/completions?api-version={api_version}
```
