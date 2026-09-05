# Rubrica de curadoria de cortes — LowOpsCast

Fonte **única** da lógica de verificação de conteúdo. Antes esta rubrica vivia duplicada
nos prompts do `gpt-5-mini` em `judge.py` e `clip_quality.py` (que chamavam o Azure AI
Foundry). O Foundry foi removido; a curadoria agora é feita **localmente pelo Claude Code**
via o harness em `tools/curate/`, aplicando exatamente esta rubrica. Ao ajustar critério de
aprovação, edite **só este arquivo**.

## Público

LowOpsCast é um podcast BR de tecnologia/DevOps. Audiência: profissionais de TI, 25–34 anos,
majoritariamente homens, Brasil. A pergunta central de cada corte é: **isso faz um estranho
parar de rolar o feed e assistir uma HISTÓRIA COMPLETA (início, meio e fim) até o fim, valendo
o tempo — não importa se tem 30s ou 3min, nem em qual rede?**

## Critério PRIMÁRIO: história completa (início, meio e fim)

Antes de qualquer payoff, o corte precisa **abrir e fechar um raciocínio auto-contido**: um estranho
entende do começo ao fim sem contexto externo, e a ideia **aterrissa** (o ponto fecha). Esse é o
critério que manda — um corte com bom conteúdo mas cortado no meio NÃO é uma boa história (ver a
seção "Completude"). A **duração é irrelevante para aprovar**: história completa longa vale tanto
quanto curta; o tempo só decide a REDE (curto → todas; longo → YouTube/LinkedIn), nunca reprova.
Qualidade de fala (filler/gaguejo) também não reprova — é só nota de polimento.

## Aprovar (`approve = true`) — precisa de PELO MENOS UM payoff concreto

1. **Insight técnico específico e útil** — conhecimento sobre uma tecnologia OU uma técnica
   prática replicável de uso de ferramentas/IA no dia a dia (ex.: "peça pra IA explicar como
   se fosse pra uma criança e vá refinando até entender" conta, mesmo sem jargão).
2. **Conselho de carreira acionável** — dica pontual (certificações, ATS, mudança de carreira)
   OU um roteiro/trilha de carreira completo e concreto ("do zero ao MBA, esses são os passos").
3. **Humor genuíno sobre a rotina de TI/DevOps** (ex.: "deploy sexta 17h59", crise de produção).
4. **Fato surpreendente ou curiosidade regional** (ex.: Pomerode, Floripa, Brasil × exterior).
5. **Virada de história genuinamente inesperada com LIÇÃO clara e explícita no final.**
6. **Fato pessoal/biográfico surpreendente** que funciona como gancho de curiosidade, mesmo
   sem lição explícita (ex.: uma virada de carreira que ninguém adivinharia).
7. **Mensagem relacionável/inspiracional** entregue com convicção, que gera identificação real
   (ex.: conselho sobre visibilidade profissional, reflexão sobre compartilhar conhecimento).
8. **Alerta genuíno sobre um risco real de carreira/aprendizado**, mesmo sem a técnica detalhada
   de como evitá-lo (ex.: "iniciante que usa IA sem calma pula fundamentos e monta base fraca").
9. **Gestão de pessoas / liderança** — conteúdo on-brand para quem é (ou quer ser) tech lead:
   transição de IC para líder, cuidar de pessoas (1:1, PDI), dar accountability ao time, entender
   as limitações pessoais de quem você lidera, formar/reter time. É payoff válido por si só — não
   trate como "genérico" só porque é soft skill; para esse público é carreira concreta.

## Reprovar (`approve = false`)

- Anedota pessoal genérica sem lição/insight claro ("quando criança eu gostava de computador
  e ganhei o do meu tio").
- História sem virada nem payoff; conteúdo raso que não ensina, não surpreende, não diverte.
- Corte que só faz sentido com contexto externo que ele mesmo não dá (incompleto).

## Reprovar SEMPRE (prioridade sobre qualquer substância)

- **Crítica negativa nomeando um concorrente/fornecedor específico** (ex.: "Azure é ruim/lixo",
  comparação depreciativa contra uma marca nomeada) → risco de imagem para o canal.
  Elogiar um concorrente nomeado é OK; o que reprova é a crítica negativa nomeada.
  Use a flag `critica_concorrente_nomeado`.

## Completude do corte — "abre e fecha o raciocínio" (eixo à parte)

A OpusClip às vezes corta a ideia no meio: o corte **começa** numa conjunção ("aí", "então", "mas",
"porque", "que", "só que"…) puxando algo que não foi dito, ou **termina** antes do raciocínio fechar
(o payoff é anunciado mas não aterrissa). Avalie sempre: **esse corte abre E fecha um raciocínio
auto-contido?**

- Se **não fecha** (cortado no começo ou no fim) MAS tem payoff bom → **mantém `approve=true`** e
  adiciona a flag **`corte_no_meio`**. É "manter e sinalizar": o conteúdo vale, mas precisa de ajuste
  de in/out point no editor antes de postar. NÃO reprova por isso — é um eixo separado, como o
  polimento de fala.
- Se além de cortado **não há payoff** (é só um fragmento solto) → aí sim reprova com `incompleto`.

`corte_no_meio` é a única flag que convive com `approve=true`; as demais `content_flags`
acompanham reprovações.

## Regra de ouro

**"A fala flui bem e é coerente" NÃO é critério de aprovação** — isso é só qualidade de edição.
O `approve` reflete EXCLUSIVAMENTE a substância do CONTEÚDO. Qualidade de fala (pausas,
repetições, fillers, gaguejo) entra só como nota de polimento em `speech_flags`, nunca decide
o `approve`. **Na dúvida, reprove.**

## Contrato de saída (por corte)

```json
{
  "id": "<id completo do corte>",
  "approve": true,
  "final_score": 0,
  "content_flags": ["sem_payoff", "generico", "anedota_fraca", "fora_do_tema", "previsivel",
                    "sem_insight", "gancho_fraco", "incompleto", "critica_concorrente_nomeado"],
  "speech_flags": ["repeticao", "pausas", "filler", "gaguejo"],
  "reason": "frase curta em PT-BR explicando o approve, com foco em CONTEÚDO"
}
```

- `final_score` (0–100): força do CONTEÚDO (não da fala). Serve de ranking para o top-N por rede.
- `content_flags` / `speech_flags`: zero ou mais dos valores enumerados acima.
- `reason`: uma frase, justificando pelo conteúdo.
