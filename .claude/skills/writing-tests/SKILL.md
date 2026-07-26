---
name: writing-tests
description: Convenções para escrever teste novo neste repo — não há biblioteca de mock HTTP, o padrão é substituir o cliente inteiro via monkeypatch no módulo que o usa, e os handlers engolem exceção devolvendo 500 opaco. Use ao criar ou corrigir teste em src/tests/, ao adicionar contador/histograma de telemetria, ao investigar teste que falha com 500 sem traceback ou com mock que nunca é chamado, e quando o usuário pedir teste, cobertura ou disser que um teste está quebrado.
---

# Escrever teste que passa aqui

Os comandos de execução e o que deixa o CI vermelho estão em `shipping-changes`. Esta skill é sobre
**como fazer o teste funcionar**.

## Não existe biblioteca de mock HTTP — e não vai existir de graça

`src/requirements.txt` não tem `respx`, `pytest-httpx`, `responses` nem `unittest.mock` como
dependência de teste, e o CI instala exatamente `requirements.txt` + `pytest`. Esse arquivo é o
requirements de **runtime da Function App** — adicionar lib de teste nele coloca peso no pacote de
deploy só para um teste passar. Não faça isso.

Duas técnicas sancionadas:

**1. Substituir o cliente inteiro** (padrão para teste de handler):

```python
monkeypatch.setattr(function_app, "OpusClient", FakeClient)
```

**2. Monkeypatch dos métodos privados numa instância real** (padrão para testar o próprio
`OpusClient`):

```python
client = OpusClient()
monkeypatch.setattr(client, "_put", lambda path, json: calls.append((path, json)) or "")
```

## Patch no módulo que USA, não no que define

`function_app` faz `from shared.X import y`, então o símbolo vive em `function_app`:

```python
monkeypatch.setattr(function_app, "OpusClient", FakeClient)        # ✅
monkeypatch.setattr(function_app, "build_schedule_plan", fake)     # ✅
monkeypatch.setattr(function_app, "send_summary_email", fake)      # ✅
monkeypatch.setattr(shared.opus_client, "OpusClient", FakeClient)  # ❌ no-op
```

Mesma regra em `library_report`, que importou o símbolo em `library_report.py:19-26`:

```python
monkeypatch.setattr(library_report, "llm_assess", fake_llm)        # ✅
monkeypatch.setattr(shared.clip_quality, "llm_assess", fake_llm)   # ❌ no-op
```

## A armadilha nº 1: 500 opaco sem traceback

Os dois handlers embrulham tudo num `except Exception` e devolvem 500 com mensagem genérica
(`function_app.py:540-547` e `:603-610`). Ao mesmo tempo, `OpusClient.__init__` faz
`os.environ["OPUSCLIP_API_KEY"]` (`opus_client.py:46`) — `KeyError` se a env var faltar.

Resultado: **teste de handler que esquece de patchear `OpusClient` falha como
`500 {"error": "Falha interna ao processar agendamento"}`, sem stack no assert.** É
indistinguível de um bug de lógica, e bissectar o handler é perda de tempo.

Ordem de triagem quando um teste de handler dá 500 inesperado:

1. `OpusClient` está patcheado? (é a causa em quase todo caso)
2. O alvo do patch é o módulo certo — `function_app`, não `shared.*`?
3. Ainda opaco? Ler a exceção real via `caplog` — o handler **loga** `exc` antes de devolver 500.

## Classe ou `lambda`: escolha carrega intenção

O handler chama `OpusClient()`. Passar a **classe** funciona quando o fake é stateless:

```python
monkeypatch.setattr(function_app, "OpusClient", FakeClient)
```

Passar `lambda: instancia` é obrigatório quando o teste precisa **inspecionar o fake depois**:

```python
fake_client = FakeClient(...)
monkeypatch.setattr(function_app, "OpusClient", lambda: fake_client)
...
assert fake_client.updated == [...]      # só possível com a instância na mão
```

## Telemetria: use a fixture, e registre meter novo nela

`src/tests/conftest.py` expõe a fixture `patch_telemetry`, que neutraliza `tracer`, todos os
contadores e os histogramas de `function_app`. Dois dos três arquivos de teste de handler ainda
carregam cópias locais dos dummies (`test_function_app.py:84-96`,
`test_e2e_schedule_existing_clips.py:88-100`) — **teste novo usa a fixture**, não duplica.

A fixture **retorna** o `monkeypatch`, então o idioma é encadear nela:

```python
def test_algo(patch_telemetry):
    patch_telemetry.setattr(function_app, "OpusClient", lambda: FakeClient(...))
```

**Ao adicionar contador ou histograma** em `telemetry.py` + `function_app`, incluir o nome em
`_COUNTERS` ou `_HISTOGRAMS` no `conftest.py:42-54`. Esquecer disso não quebra o teste — ele passa
usando o **meter real**, que é pior: emissão de telemetria durante a suíte, silenciosa.

## Handlers são chamados como função comum

Sem host de Functions, sem `func start`, apesar do modelo v2 com decorator. Constrói-se um
`func.HttpRequest` na mão e chama-se a função direto. **O body precisa ser `bytes`.**

Não montar harness de host — não é como este repo testa.

## State store: desligado por omissão

Nenhum teste de handler patcheia `ScheduleStateStore`. Ele **se autodesliga** sem
`STORAGE_ACCOUNT_NAME` / `STATE_STORAGE_CONNECTION_STRING` (`state_store.py:43-48`), e é disso que os
testes dependem.

Cuidado: fazer `monkeypatch.setenv("STORAGE_ACCOUNT_NAME", ...)` num teste de handler faz o store
construir `DefaultAzureCredential` e **ir na rede** (`state_store.py:57-64`).

Para testar o store de propósito, use o bypass documentado (`test_state_store.py:24-27`):

```python
store = ScheduleStateStore.__new__(ScheduleStateStore)   # não roda __init__
store._table = FakeTable()
```

## LLM: precisa do endpoint mesmo com o fake no lugar

`LLMSettings.enabled` exige `JUDGE_AZURE_OPENAI_ENDPOINT` presente
(`clip_quality.py:138-139`), e `library_report` só entra no ramo de LLM se estiver habilitado.

Então um teste com `use_llm=True` e `llm_assess` fakeado **precisa também**
`monkeypatch.setenv("JUDGE_AZURE_OPENAI_ENDPOINT", "https://fake")`
(`test_library_report.py:102`). Sem isso o ramo não roda, `llm_used` fica `False`, e **o fake nunca
é chamado** — falha confusa, porque o mock está correto.

## O CI roda de outro diretório

| | cwd | `sys.path` |
|---|---|---|
| Local | raiz do repo | `pyproject.toml` → `pythonpath = ["src"]` |
| CI | `src/` | `PYTHONPATH: .`, comando `pytest -q tests/` |

Portanto: **nunca resolver caminho a partir do cwd** num teste. Preferir fixture inline a arquivo de
dados. A suíte é 100% offline — o CI não fornece nenhuma env var de Azure ou OpusClip.

## Validação

```bash
pytest -q                       # suíte toda, da raiz
pytest src/tests/test_x.py -q   # alvo
```
