# Curadoria — índice mestre (reconciliado com a conta OpusClip)

Reconciliado em 2026-09-04: cruzado com `list_projects()` ao vivo. **11 episódios LowOpsCast**
vivos na conta (a duplicata do #45 foi apagada pelo usuário) + **1 show separado** (Tech Floripa
Cast #010, curado a pedido específico — normalmente fora da automação LowOpsCast).
`review/_archived/` guarda a curadoria de 2 projetos já apagados da conta (não contam nos totais).

Critério primário = **história completa** (início/meio/fim), qualquer duração — duração só roteia
rede (curta ≤90s → todas; longa >90s → YouTube/LinkedIn). Rubrica em `src/shared/curation_rubric.md`.

## LowOpsCast (11 episódios)

| Ep | clips | conteúdo | **completa** | curta | longa | corte-no-meio | anti-concorrente |
|---|---:|---:|---:|---:|---:|---:|---:|
| #52 Rafael Medeiros — Dubai | 44 | 23 | **22** | 18 | 4 | 1 | 2 |
| #51 Sandro Guimarães — Clipper→K8s | 52 | 23 | **21** | 20 | 1 | 2 | 0 |
| #48 Emerson Silva — DevOps/K8s | 41 | 23 | **21** | 17 | 4 | 2 | 0 |
| #50 Julia Furst — Cloud Native global | 41 | 22 | **19** | 11 | 8 | 3 | 0 |
| #53 Igor Eulalio — Kubestronaut | 39 | 19 | **18** | 12 | 6 | 1 | 1 |
| #49 Edson Ferreira — Open Source | 40 | 17 | **16** | 15 | 1 | 1 | 1 |
| #45 Cesar "Sallah" — SRE/AWS (`P3090317kaRt`) | 45 | 25 | **16** | 13 | 3 | 9 | 0 |
| #44 Bruno Lopes — Arquitetura cloud/AWS | 47 | 17 | **15** | 15 | 0 | 2 | 0 |
| #55 Paulo Alves — DevOps além das ferramentas | 44 | 15 | **13** | 12 | 1 | 2 | 1 |
| #47 Alison Duarte — plataformas como produtos | 44 | 14 | **13** | 10 | 3 | 1 | 0 |
| #54 Fabrício Carraro — IA Sob Controle | 42 | 14 | **12** | 10 | 2 | 2 | 0 |
| **TOTAL** | **479** | **212** | **186** | **153** | **33** | **26** | **5** |

## Outro show (curado à parte, fora da automação LowOpsCast)

| | clips | conteúdo | completa | curta | longa | corte-no-meio |
|---|---:|---:|---:|---:|---:|---:|
| Tech Floripa Cast #010 — Rafael Ferreira (`P3090402YL1N`, reimportado com template novo) | 39 | 17 | 15 | 15 | 0 | 2 |

## Pendências conhecidas (não são "completo e pronto")

- **`P3090317jt4X.SdWaLEYCJ2`** (#47, "De Infraestrutura a Arquiteto AWS"): tive o in/out estendido
  via API (`timeRanges`) e a métrica local já conta como "longa completa". **Mas o vídeo físico
  ainda não foi confirmado como re-renderizado** — a API não re-renderiza por clip; só materializa
  ao salvar no editor do portal. Antes de agendar este corte, abra-o no portal, salve/exporte, e
  valide (a checagem é: `last-modified`/`x-goog-generation` do `uriForPreview` tem que mudar).
- **19 propostas de conserto de in/out** avaliadas por verificação adversarial: só 1 (o item acima)
  foi aprovada como história fechada; as outras 18 precisam de mais contexto do que cabia na janela
  de 45s analisada, ou o setup/fechamento está entrelaçado com outro assunto — não dá pra resolver
  só ajustando bordas.
- **Rigor de curadoria varia entre episódios** (múltiplas instâncias Claude julgando) — a coluna
  "completa" é a mais robusta (trava no gate + completude); "conteúdo" tem mais ruído de calibração.

Números ao vivo: `python3 tools/curate/aggregate.py` (ainda lê `review/*`, incluindo `_archived/` —
ajustar se quiser excluir automaticamente).
