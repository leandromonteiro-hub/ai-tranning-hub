# Plano de Validação — Fase 0

**Produto:** Athlete AI Training Hub (gestão de treino de MTB/ciclismo com IA)
**Fase:** 0 — Validação com 2 atletas reais, ANTES de qualquer decisão comercial
**Data do documento:** 22/06/2026
**Responsável:** Leandro Monteiro (dono do produto e atleta de teste 1)

---

## 1. Objetivos da validação

O objetivo desta fase é responder, com evidências práticas e mensuráveis, a uma única pergunta central:

> **O sistema funciona MUITO bem para 2 pessoas reais, ao ponto de justificar continuar investindo nele?**

Validar primeiro com 2 atletas (não 20, não 200) é uma decisão deliberada: queremos profundidade e qualidade de uso real, não volume. Se não funcionar bem para 2 atletas experientes que conhecem o domínio, não há por que escalar.

### Objetivos específicos

1. Confirmar que um atleta consegue **importar seu histórico do TrainingPeaks sozinho**, sem suporte técnico.
2. Confirmar que as **recomendações de treino fazem sentido** para atletas experientes.
3. Confirmar que há **uso voluntário e contínuo** (não forçado) por pelo menos 4 semanas.
4. Coletar **feedback estruturado** suficiente para decidir o futuro do produto.
5. Provar que **não há vazamento de dados** entre os dois atletas (isolamento total verificado).

### O que NÃO está em escopo nesta fase

| Fora de escopo | Motivo |
|---|---|
| Decisão de preço / modelo de cobrança | Validação vem antes de qualquer decisão comercial |
| Marketing, aquisição, landing page | Não estamos buscando usuários nesta fase |
| Escalabilidade / performance sob carga | 2 usuários não exigem otimização de infraestrutura |
| Suporte a outras plataformas (Strava, Garmin Connect, Wahoo) além de TrainingPeaks | Foco no histórico real disponível (TP) |
| Funcionalidades sociais, gamificação, rankings | Não são hipóteses críticas agora |
| Aplicativo móvel nativo | Web é suficiente para validar a hipótese central |
| Integração de pagamento, faturamento, contratos | Decisão comercial é posterior |
| Onboarding de atletas não experientes | A validação depende de avaliação por experts do domínio |

---

## 2. Perfil dos atletas de teste e critérios de seleção

São exatamente **2 atletas**, escolhidos para maximizar a qualidade do feedback técnico, não a representatividade de mercado.

### Atleta 1 — Dono do produto

| Atributo | Valor |
|---|---|
| Experiência em MTB | 10+ anos |
| Histórico de dados | 5–6 anos de TrainingPeaks |
| Papel | Dono do produto e usuário experiente |
| Por que está no teste | Conhece o domínio a fundo; consegue avaliar se as recomendações fazem sentido; tem o histórico mais rico para importar |

### Atleta 2 — Atleta externo experiente

| Atributo | Valor alvo |
|---|---|
| Experiência em ciclismo/MTB | Mínimo 3 anos de treino estruturado |
| Histórico de dados | Possui histórico exportável do TrainingPeaks (CSV + FIT) |
| Independência | Capaz de usar ferramentas web sem acompanhamento |
| Papel | Usuário externo, sem viés de "dono" |
| Por que está no teste | Valida que o sistema funciona para alguém que NÃO construiu o produto e não tem contexto interno |

### Critérios de seleção do atleta 2

- Treina de forma estruturada (segue plano, não treina "no feeling").
- Tem opinião crítica e disposição para dar feedback honesto, inclusive negativo.
- Possui conta TrainingPeaks ativa com pelo menos 1 ano de dados exportáveis.
- Compromete-se a usar o sistema por 4 semanas e responder aos check-ins.
- Não tem acesso ao código nem ao backend (garante isolamento real do ponto de vista de produto).

---

## 3. Protocolo de onboarding

O onboarding é o primeiro teste crítico: **o atleta deve conseguir importar seu histórico sozinho.** Qualquer necessidade de suporte técnico durante o onboarding é registrada como ocorrência.

### Pré-requisitos (entregues ao atleta antes de começar)

- Link de acesso ao sistema e credenciais da sua conta.
- Um guia curto (1 página) de como exportar dados do TrainingPeaks.
- Nenhuma orientação verbal ao vivo. Tudo deve estar no sistema ou no guia escrito.

### Passo a passo de importação (TrainingPeaks → sistema)

1. **Exportar do TrainingPeaks**
   - Exportar o histórico de treinos em **CSV** (resumo de sessões: data, duração, TSS, IF, NP, distância, etc.).
   - Exportar/baixar os **arquivos FIT** das sessões (dados detalhados: potência, FC, cadência, GPS por segundo).
2. **Criar/acessar a conta** no Athlete AI Training Hub.
3. **Upload do CSV** de resumo histórico na tela de importação.
4. **Upload em lote dos arquivos FIT** (pasta/zip).
5. **Validação visual:** o sistema mostra um resumo do que foi importado (nº de treinos, período coberto, métricas reconhecidas) para o atleta conferir.
6. **Confirmação:** o atleta confirma que os dados batem com o histórico que ele conhece.

### O que medir durante o onboarding

| Métrica | Como medir | Meta |
|---|---|---|
| Tempo total de onboarding | Cronometrar do login inicial à confirmação dos dados | < 30 min |
| Nº de erros de importação | Contagem de falhas (CSV rejeitado, FIT corrompido, parsing incorreto) | Registrar todos |
| Taxa de erro de importação | Treinos com erro ÷ total de treinos importados | < 5% |
| Precisou de suporte? | Sim/Não + descrição da intervenção | Não (0 intervenções) |
| Pontos de fricção | Notas qualitativas de onde o atleta hesitou ou travou | Lista priorizada |
| Cobertura dos dados | % do histórico esperado que de fato apareceu no sistema | >= 95% |

> **Regra:** se o atleta enviar uma mensagem pedindo ajuda, isso conta como "precisou de suporte". O suporte é prestado (não deixamos o atleta travado), mas a ocorrência é registrada e analisada.

---

## 4. O que medir (métricas de validação)

Três grupos de métricas: **uso**, **qualidade percebida** e **operação/saúde técnica**.

### 4.1 Métricas de uso

| Métrica | Definição | Frequência |
|---|---|---|
| Logins | Nº de sessões de acesso por atleta | Diária (agregada por semana) |
| Treinos importados | Total acumulado de sessões no sistema | Inicial + incrementos |
| Recomendações vistas | Nº de recomendações que o atleta efetivamente abriu/visualizou | Por evento |
| Recomendações aceitas | Recomendações executadas como sugeridas | Por evento |
| Recomendações rejeitadas | Recomendações descartadas | Por evento |
| Recomendações modificadas | Recomendações ajustadas antes de executar | Por evento |
| Dias ativos por semana | Dias com qualquer interação significativa | Semanal |

### 4.2 Qualidade percebida das recomendações

| Métrica | Definição |
|---|---|
| % "faz sentido" | Recomendações avaliadas com rating >= 4 (numa escala 1–5) sobre o total avaliado |
| Rating médio das recomendações | Média dos ratings 1–5 |
| Taxa de aceitação | Aceitas ÷ (Aceitas + Rejeitadas + Modificadas) |
| Resultado observado pós-execução | % de recomendações executadas cujo resultado foi avaliado como positivo |

### 4.3 Operação e satisfação

| Métrica | Definição | Meta |
|---|---|---|
| Tempo de onboarding | (ver seção 3) | < 30 min |
| Taxa de erro de importação | (ver seção 3) | < 5% |
| Incidentes de isolamento | Qualquer caso de dado de um atleta visível para o outro | 0 |
| NPS / satisfação | "De 0 a 10, quanto recomendaria este sistema a outro atleta?" | >= 8 por ambos |
| CSAT final | Satisfação geral 1–5 no questionário final | >= 4 por ambos |

---

## 5. Como coletar feedback

A coleta de feedback tem **três instrumentos**, em camadas, do mais granular ao mais geral.

### 5.1 Feedback estruturado em cada recomendação (granular)

Em **toda** recomendação apresentada, o atleta pode/deve registrar:

1. **Rating de sentido (1–5):** "Esta recomendação faz sentido para você agora?"
   - 1 = Não faz sentido nenhum · 5 = Faz total sentido
2. **Ação tomada:** Aceitei / Rejeitei / Modifiquei.
3. **Comentário livre (opcional):** "Por quê? O que você mudaria?"
4. **Resultado observado (preenchido DEPOIS da execução):**
   - "Como foi o treino na prática?" → Melhor que esperado / Conforme esperado / Pior que esperado.
   - Comentário livre sobre o resultado.

Este é o instrumento mais importante: liga a recomendação ao seu desfecho real.

### 5.2 Check-in semanal qualitativo

Uma vez por semana (mesma janela combinada), cada atleta responde a 4 perguntas curtas:

1. O que funcionou bem esta semana no sistema?
2. O que te incomodou ou atrapalhou?
3. Alguma recomendação te surpreendeu (positiva ou negativamente)? Qual?
4. Você voltaria a usar o sistema na próxima semana sem ninguém te lembrar? (Sim/Não + por quê)

Formato: 10–15 min, por mensagem ou formulário. Respostas registradas e datadas.

### 5.3 Questionário final (ao fim das 4 semanas)

Aplicado no fim da semana 4. Mistura escala e aberto.

**Bloco A — Quantitativo (escala 1–5, salvo indicado)**
1. As recomendações fizeram sentido para mim como atleta experiente.
2. Confiei nas recomendações do sistema.
3. A importação do meu histórico foi fácil.
4. O sistema me poupou tempo / esforço de planejamento.
5. Satisfação geral com o sistema (CSAT).
6. **NPS:** De 0 a 10, quanto recomendaria a outro atleta?

**Bloco B — Qualitativo (aberto)**
7. Qual foi a recomendação mais útil que o sistema te deu? Por quê?
8. Qual foi a pior recomendação? O que estava errado?
9. O que faria você usar este sistema todo dia?
10. O que está faltando para você confiar 100%?
11. Se o sistema deixasse de existir amanhã, você sentiria falta? Por quê?
12. Você pagaria por isso? (apenas opinião — sem compromisso). Quanto faria sentido?

> A pergunta 11 ("sentiria falta?") é um proxy clássico de product-market fit e ajuda na decisão pós-validação.

---

## 6. Cronograma de 4 semanas

| Semana | O que acontece | O que se mede |
|---|---|---|
| **Semana 0 (preparação)** | Seleção e confirmação do atleta 2; envio de credenciais e guia de exportação; verificação de isolamento ANTES de qualquer dado real entrar | Setup pronto; testes de isolamento passando |
| **Semana 1 — Onboarding + uso inicial** | Cada atleta importa seu histórico sozinho; começa a receber e avaliar recomendações | Tempo de onboarding, taxa de erro de importação, necessidade de suporte, primeiras recomendações avaliadas; check-in 1 |
| **Semana 2 — Uso em ritmo** | Uso contínuo; recomendações sendo aceitas/rejeitadas/modificadas; registro de resultado pós-execução | Métricas de uso, % "faz sentido", taxa de aceitação; check-in 2 |
| **Semana 3 — Consolidação** | Uso continua; observar se o atleta volta sozinho (uso voluntário); acompanhar resultados das recomendações já executadas | Dias ativos/semana, resultado observado pós-execução, consistência; check-in 3 |
| **Semana 4 — Fechamento** | Última semana de uso; aplicação do questionário final | Todas as métricas consolidadas, NPS/CSAT, questionário final; check-in 4 |
| **Pós-semana 4 — Decisão** | Consolidação dos dados e reunião de decisão | Comparação contra critérios de sucesso/falha (seção 7) |

Verificação de isolamento entre atletas é executada **continuamente** (não só na semana 0): automatizada a cada deploy e manualmente uma vez por semana.

---

## 7. Critérios de sucesso e de falha (quantificados)

A decisão é baseada em limiares concretos. Para **SUCESSO**, todos os critérios obrigatórios devem ser atendidos.

### 7.1 Critérios de sucesso

| # | Critério | Limiar | Obrigatório? |
|---|---|---|---|
| 1 | Importação sem suporte técnico | Ambos os atletas importam sem intervenção (0 chamados de suporte de onboarding) | Sim |
| 2 | Recomendações fazem sentido | >= 70% das recomendações avaliadas com rating >= 4 ("faz sentido") | Sim |
| 3 | Uso voluntário contínuo | Cada atleta usa o sistema em >= 3 das 4 semanas (dias ativos > 0 na semana) | Sim |
| 4 | Feedback positivo o suficiente | NPS >= 8 e CSAT >= 4 para ambos; resposta positiva à pergunta "sentiria falta?" | Sim |
| 5 | Isolamento total | 0 incidentes de vazamento de dados entre os dois atletas | Sim (bloqueante) |
| 6 | Onboarding rápido | Tempo de onboarding < 30 min para ambos | Desejável |
| 7 | Importação confiável | Taxa de erro de importação < 5% | Desejável |
| 8 | Recomendações úteis na prática | >= 60% das recomendações executadas com resultado "conforme" ou "melhor que esperado" | Desejável |

### 7.2 Critérios de falha

A validação é considerada **falha** se qualquer um ocorrer:

- **Qualquer** incidente de vazamento de dados entre atletas (critério bloqueante absoluto).
- < 50% das recomendações avaliadas como "faz sentido".
- Algum atleta abandona o uso (uso em <= 1 das 4 semanas).
- NPS médio < 6 ou CSAT < 3 de ambos os atletas.
- Onboarding impossível sem suporte intensivo e repetido (o atleta não consegue importar de jeito nenhum sozinho).

### 7.3 Zona intermediária

Se os critérios obrigatórios forem atendidos mas os desejáveis não (ex: onboarding levou 45 min, ou taxa de erro 8%), o resultado é **"evoluir com ressalvas"** — segue, mas com backlog claro de correção antes de qualquer escala.

---

## 8. Plano de verificação de isolamento entre atletas

O isolamento (multi-tenant) é um critério **bloqueante**. Nenhum dado, recomendação, treino ou métrica de um atleta pode ser visível, consultável ou recomendável para o outro.

### 8.1 Testes automatizados

Executados em cada deploy e diariamente:

| Teste | Verifica |
|---|---|
| Filtro por tenant em todas as consultas | Toda query de leitura inclui o identificador do atleta; nenhuma retorna linhas de outro atleta |
| Tentativa de acesso cruzado por ID | Requisição autenticada como atleta A pedindo recurso (treino/recomendação) do atleta B retorna 403/404, nunca o dado |
| Isolamento na importação | Upload de arquivo por A nunca é associado a B |
| Isolamento na geração de recomendação | O motor de recomendação só enxerga os dados do próprio atleta |
| Vazamento em agregações/relatórios | Médias, históricos e gráficos não somam dados de outro tenant |

### 8.2 Verificação manual (semanal)

1. Logar como atleta A e tentar, deliberadamente, acessar dados de B (manipulando IDs na URL/API). Confirmar bloqueio.
2. Conferir que contagens (nº de treinos, período do histórico) batem exatamente com o que cada atleta importou — nenhum "treino fantasma".
3. Revisar logs de acesso buscando qualquer requisição que tenha cruzado tenants.
4. Conferir que recomendações geradas para A não referenciam nenhum dado de B.

### 8.3 Registro

Toda verificação (automática e manual) gera um registro datado com resultado PASS/FAIL. **Qualquer FAIL interrompe a validação** até correção e nova verificação.

---

## 9. Riscos da validação e mitigação

| Risco | Impacto | Probabilidade | Mitigação |
|---|---|---|---|
| Exportação do TrainingPeaks falhar ou vir incompleta | Onboarding bloqueado | Média | Guia de exportação testado antes; suporte a CSV + FIT; validação visual pós-import |
| Atleta 2 desiste no meio | Perde-se 50% da amostra | Média | Selecionar atleta comprometido; check-ins semanais para detectar desengajamento cedo |
| Recomendações "genéricas" que não convencem experts | Falha no critério 2 | Média | Coletar comentário em cada rejeição para entender o porquê e iterar |
| Viés do dono (atleta 1) inflar avaliação | Resultado não confiável | Alta | Dar peso especial ao atleta 2 (externo); separar métricas por atleta na análise |
| Amostra pequena (n=2) gera conclusão frágil | Decisão errada | Alta (inerente) | Aceitar que é validação qualitativa de profundidade, não estatística; exigir sinais fortes e consistentes |
| Bug de isolamento descoberto tarde | Bloqueante | Baixa | Testes automatizados desde a semana 0, antes de dado real entrar |
| Falta de uso por falta de "motivo de voltar" | Falha no critério 3 | Média | Check-in mede explicitamente "voltaria sem ser lembrado?"; identificar o gancho de retorno |
| Confundir cortesia com aprovação real | Falsa validação | Média | Perguntas duras no questionário ("pior recomendação", "sentiria falta?") e foco em comportamento (uso real) sobre opinião |

---

## 10. Decisão pós-validação

Ao fim da semana 4, os dados são consolidados e comparados contra a seção 7. A decisão cai em uma de três faixas:

### EVOLUIR o produto

**Quando:** todos os critérios obrigatórios atendidos (importação sem suporte, >= 70% das recomendações "fazem sentido", uso em >= 3 das 4 semanas por ambos, NPS >= 8 / CSAT >= 4, 0 incidentes de isolamento) e resposta positiva à pergunta "sentiria falta?".

**O que significa:** há sinal forte de valor real. Avançar para a próxima fase — corrigir as ressalvas do backlog e só então considerar ampliar o número de atletas e iniciar discussão comercial.

### PIVOTAR

**Quando:** o isolamento está sólido e o onboarding funciona, MAS o núcleo de valor falha — recomendações entre 50% e 70% de "faz sentido", ou uso morno (apenas 2 das 4 semanas), ou feedback ambíguo (NPS 6–7).

**O que significa:** a base técnica serve, mas a hipótese de valor (qualidade/utilidade das recomendações) precisa ser reformulada. Ajustar o motor de recomendação, mudar o foco do produto ou o perfil de atleta, e revalidar com novo ciclo curto antes de qualquer escala.

### PARAR

**Quando:** qualquer critério de falha (seção 7.2) ocorre — vazamento de dados entre atletas, < 50% das recomendações fazendo sentido, abandono de uso, ou NPS médio < 6.

**O que significa:** não há sinal suficiente de que o sistema funciona muito bem nem para 2 pessoas. Não escalar. Documentar os aprendizados, decidir conscientemente entre uma reformulação profunda (volta à prancheta) ou encerramento do projeto, sem injetar mais investimento sob premissas não validadas.

---

### Resumo da régua de decisão

| Faixa | Recomendações "fazem sentido" | Uso (de 4 semanas) | NPS | Isolamento | Decisão |
|---|---|---|---|---|---|
| Verde | >= 70% | >= 3 por ambos | >= 8 | 0 incidentes | **Evoluir** |
| Amarela | 50–69% | 2 por ambos | 6–7 | 0 incidentes | **Pivotar** |
| Vermelha | < 50% | <= 1 por algum | < 6 | Qualquer incidente | **Parar** |
