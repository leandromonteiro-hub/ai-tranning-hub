# Integrações de API — Athlete AI Training Hub

> Documento de pesquisa e referência para integração com plataformas de treino, dispositivos e plataformas de saúde/recuperação no ecossistema de ciclismo e endurance.

---

## ⚠️ AVISO IMPORTANTE (Disclaimer)

**Os termos, limites, modelos de autenticação, custos e políticas de acesso das APIs descritas neste documento mudam com frequência e sem aviso prévio.**

Este documento foi elaborado com base em conhecimento consolidado dos programas de desenvolvedores dessas plataformas até o limite de conhecimento do autor/modelo. **Nenhuma decisão de implementação deve ser tomada exclusivamente com base neste documento.**

Antes de iniciar qualquer integração:

1. **TODA** integração descrita aqui **DEVE** ser reverificada contra a documentação oficial e vigente do programa de desenvolvedores da plataforma.
2. Verifique limites de taxa (rate limits), custos atuais, requisitos de aprovação/parceria e cláusulas comerciais (especialmente sobre armazenamento, agregação e revenda de dados).
3. Confirme as exigências de marca (branding), exibição obrigatória de logos ("Powered by"/"Compatible with") e atribuição.
4. Revise os Termos de Serviço e o Contrato de API (API Agreement) de cada plataforma, pois eles prevalecem sobre qualquer informação aqui.

> Considere este documento como um **mapa estratégico inicial**, não como especificação técnica definitiva.

---

## Índice

- [1. Plataformas de Treino](#1-plataformas-de-treino)
- [2. Dispositivos](#2-dispositivos)
- [3. Saúde e Recuperação](#3-saúde-e-recuperação)
- [4. Matriz Comparativa](#4-matriz-comparativa)
- [5. Estratégias para APIs Restritas ou Inexistentes](#5-estratégias-para-apis-restritas-ou-inexistentes)
- [6. Roadmap Recomendado de Integração para o MVP](#6-roadmap-recomendado-de-integração-para-o-mvp)

---

## 1. Plataformas de Treino

### 1.1 Strava

| Item | Detalhe |
|------|---------|
| **API oficial?** | Sim — API REST **pública** (Strava API v3). |
| **SDK disponível?** | Sem SDK oficial mantido pela Strava; existem SDKs comunitários (Python `stravalib`, JS, etc.). |
| **Autenticação** | **OAuth2** (authorization code flow), com escopos (`read`, `activity:read`, `activity:read_all`, `activity:write` etc.). |
| **Dados acessíveis** | Atividades (resumo e detalhe), streams (potência, FC, cadência, GPS, altitude), segmentos, esforços em segmentos, perfil do atleta, gear, rotas, kudos/comentários. |
| **Limites de uso e custo** | Gratuito para uso geral, mas com **rate limits restritivos** (padrão histórico: ~100 requisições por 15 min e ~1.000/dia por aplicação; limites globais para a app). Aplicações grandes precisam negociar aumento. |
| **Restrições comerciais** | **Rigorosas.** Restrições sobre **armazenar/agregar** dados de atividades de terceiros, sobre **análise em massa (bulk)** e mineração de dados, sobre exibir dados de um atleta para outro usuário, e exigências fortes de **branding/atribuição** ("Powered by Strava", uso correto de logos). Proibição de criar produtos que substituam funções centrais do Strava. |
| **Webhook disponível?** | Sim — **Push subscriptions** (webhooks) para eventos de criação/atualização/exclusão de atividades e desautorização. |
| **Exportação manual** | FIT / TCX / GPX por atividade (download individual); exportação em massa via "Bulk Export" da conta. |
| **Risco de bloqueio/mudança** | **Médio-Alto.** Histórico de mudanças unilaterais de termos e enrijecimento de políticas de uso de dados. App pode ser suspensa por violação de branding ou de cláusulas de dados. |
| **Estratégia recomendada inicial** | **Excelente primeira integração OAuth2.** Implementar leitura de atividades + webhooks. Atenção máxima às cláusulas de armazenamento/agregação e às regras de marca. |

---

### 1.2 Garmin Connect

| Item | Detalhe |
|------|---------|
| **API oficial?** | **Não há API pública geral.** Acesso somente via **Garmin Connect Developer Program** (Health API, Activity API, Training API) mediante **aprovação/parceria**. |
| **SDK disponível?** | Bibliotecas/ferramentas fornecidas a parceiros aprovados; sem SDK público aberto. (Para dispositivos, há o Garmin SDK / Connect IQ, que é outro escopo.) |
| **Autenticação** | Historicamente **OAuth 1.0a** para as APIs de parceiro; confirmar fluxo atual com a Garmin. |
| **Dados acessíveis** | (Para parceiros) atividades, dados de saúde/wellness (passos, sono, FC, stress, Body Battery), métricas de treino. Conjunto depende da API contratada (Health vs. Activity vs. Training). |
| **Limites de uso e custo** | Definidos por contrato de parceria; processo de avaliação e aprovação. Não autoatendimento. |
| **Restrições comerciais** | Altas — uso sujeito a contrato; restrições de redistribuição. |
| **Webhook disponível?** | Sim, para parceiros aprovados — modelo **ping/pull** (notificação + busca dos dados). |
| **Exportação manual** | FIT / TCX / GPX por atividade via Garmin Connect (download individual). |
| **Risco de bloqueio/mudança** | **Alto** — dependência total de aprovação de parceria; barreira de entrada elevada. |
| **Estratégia recomendada inicial** | **Adiar.** No curto prazo, usar **upload manual de arquivos FIT** ou ingestão via Strava (que já recebe sync do Garmin). Buscar parceria oficial apenas em fase posterior. |

---

### 1.3 TrainingPeaks

| Item | Detalhe |
|------|---------|
| **API oficial?** | Sim, **existe**, porém **restrita a parceiros** (acesso à TrainingPeaks API mediante parceria/aprovação). |
| **SDK disponível?** | Recursos a parceiros; sem SDK público aberto. |
| **Autenticação** | OAuth2 para parceiros aprovados (confirmar). |
| **Dados acessíveis** | (Para parceiros) workouts planejados e executados, métricas (TSS, IF, CTL/ATL/TSB), planos de treino. |
| **Limites de uso e custo** | Por contrato de parceria. |
| **Restrições comerciais** | Restrições típicas de parceria; foco em integrações que complementam, não competem. |
| **Webhook disponível?** | Disponível a parceiros (confirmar escopo). |
| **Exportação manual** | Exportação de workouts em **CSV/estruturado**; arquivos FIT/TCX/GPX por atividade. Exportação de dados estruturados (calendário/PMC) é comum. |
| **Risco de bloqueio/mudança** | **Médio-Alto** (acesso depende de aprovação). |
| **Estratégia recomendada inicial** | **Começar pela importação de CSV/arquivos exportados** pelo próprio atleta/treinador. Parceria de API fica para fase posterior. |

---

### 1.4 WKO5

| Item | Detalhe |
|------|---------|
| **API oficial?** | **Inexistente** — WKO5 é aplicativo **desktop** de análise (do ecossistema TrainingPeaks), sem API de nuvem. |
| **SDK disponível?** | Não. |
| **Autenticação** | N/A. |
| **Dados acessíveis** | Dados locais no banco do desktop; não há acesso programático via nuvem. |
| **Limites/custo** | N/A (licença de software). |
| **Restrições comerciais** | N/A. |
| **Webhook disponível?** | Não. |
| **Exportação manual** | Importa/exporta arquivos (FIT/TCX/GPX/CSV); dados sincronizados via TrainingPeaks. |
| **Risco de bloqueio/mudança** | Baixo (não há integração ativa a quebrar). |
| **Estratégia recomendada inicial** | **Não integrar diretamente.** Tratar via arquivos exportados ou via TrainingPeaks. |

---

### 1.5 Intervals.icu

| Item | Detalhe |
|------|---------|
| **API oficial?** | Sim — **amigável a desenvolvedores e atletas**, documentação pública. |
| **SDK disponível?** | Sem SDK oficial completo; API REST simples e bem documentada, fácil de consumir diretamente. |
| **Autenticação** | **API key** (por atleta) **e OAuth2** para aplicações. |
| **Dados acessíveis** | Atividades, wellness (sono, HRV, FC repouso, peso), métricas de carga (Fitness/Fatigue/Form ~ CTL/ATL), workouts planejados, eventos do calendário. |
| **Limites de uso e custo** | Gratuito/generoso; plataforma orientada à comunidade. |
| **Restrições comerciais** | Poucas; postura aberta. (Confirmar termos atuais antes de uso comercial.) |
| **Webhook disponível?** | Verificar documentação atual; o foco principal é a API REST. |
| **Exportação manual** | FIT / TCX / GPX por atividade; exportação de dados; consumo direto via API. |
| **Risco de bloqueio/mudança** | **Baixo** — postura historicamente aberta e pró-desenvolvedor. |
| **Estratégia recomendada inicial** | **Forte candidata para integração precoce.** Excelente custo-benefício; ótima fonte de dados de carga e wellness consolidados. |

---

### 1.6 TrainerRoad

| Item | Detalhe |
|------|---------|
| **API oficial?** | **Não há API pública** documentada para terceiros. |
| **SDK disponível?** | Não. |
| **Autenticação** | N/A (sem API pública). |
| **Dados acessíveis** | Sem acesso programático oficial; dados via sync para outras plataformas (ex.: envia atividades para Strava/TrainingPeaks). |
| **Limites/custo** | N/A. |
| **Restrições comerciais** | N/A (sem API). |
| **Webhook disponível?** | Não. |
| **Exportação manual** | Atividades exportáveis (FIT/TCX) e sincronização para outras plataformas. |
| **Risco de bloqueio/mudança** | N/A. |
| **Estratégia recomendada inicial** | **Integração indireta** via Strava/TrainingPeaks ou upload de arquivos. Sem integração direta no MVP. |

---

### 1.7 Today's Plan

| Item | Detalhe |
|------|---------|
| **API oficial?** | Existe API de parceiro/integração, **restrita** (mediante contato/parceria). |
| **SDK disponível?** | Recursos a parceiros; sem SDK público aberto. |
| **Autenticação** | OAuth2/token para parceiros (confirmar). |
| **Dados acessíveis** | Workouts, métricas de carga, planos, dados de atletas (para parceiros). |
| **Limites/custo** | Por acordo de parceria. |
| **Restrições comerciais** | Restrições de parceria. |
| **Webhook disponível?** | Verificar com a plataforma. |
| **Exportação manual** | FIT/TCX/GPX/CSV; sincroniza com Garmin/Wahoo/TrainingPeaks. |
| **Risco de bloqueio/mudança** | Médio (depende de parceria). |
| **Estratégia recomendada inicial** | **Adiar.** Tratar via arquivos exportados; avaliar parceria só se houver demanda relevante de usuários. |

---

### 1.8 Golden Cheetah

| Item | Detalhe |
|------|---------|
| **API oficial?** | **Sem API de nuvem.** Software **open-source desktop**; dados ficam locais. |
| **SDK disponível?** | Não há SDK de nuvem; possui API REST **local** (servidor local interno) e código aberto. |
| **Autenticação** | N/A (acesso local). |
| **Dados acessíveis** | Todos os dados locais do atleta; formatos de arquivo abertos; modelo de dados acessível por ser open-source. |
| **Limites/custo** | Gratuito (open-source, GPL). |
| **Restrições comerciais** | Mínimas (atentar à licença GPL ao reutilizar código). |
| **Webhook disponível?** | Não (aplicação local). |
| **Exportação manual** | **Excelente** — FIT/TCX/GPX/CSV/JSON; formatos abertos e bem documentados. |
| **Risco de bloqueio/mudança** | **Muito baixo** (open-source, sem dependência de fornecedor). |
| **Estratégia recomendada inicial** | **Integração via arquivos** (import/export). Ótima referência de modelo de dados e formatos abertos. |

---

## 2. Dispositivos

> Observação: dispositivos normalmente expõem dados **através da plataforma de nuvem do fabricante** (ex.: Garmin → Garmin Connect). A integração direta com o hardware geralmente exige app móvel + SDK específico (BLE/ANT+), fora do escopo de um backend web inicial.

### 2.1 Garmin (dispositivos)

- **API oficial?** Via **Garmin Connect** (ver seção 1.2) — sem API pública geral; parceria necessária. Para o dispositivo em si, há **Connect IQ SDK** (apps no relógio/ciclocomputador) e FIT SDK (parsing de arquivos).
- **Autenticação:** OAuth (programa de parceria); N/A para parsing local de FIT.
- **Dados:** atividades, wellness, saúde (para parceiros).
- **Webhook:** ping/pull para parceiros.
- **Exportação manual:** FIT/TCX/GPX.
- **Risco:** Alto (dependência de parceria).
- **Estratégia inicial:** **Upload manual de FIT** + **FIT SDK** para parsing; sync via Strava como ponte.

### 2.2 Wahoo

- **API oficial?** Sim — **Wahoo Cloud API** (modelo de parceiro/OAuth2).
- **SDK:** recursos a parceiros; sem SDK público amplo.
- **Autenticação:** **OAuth2**.
- **Dados:** workouts/atividades, planos, dados de treino sincronizados na nuvem Wahoo.
- **Limites/custo:** por aplicação/parceria (confirmar).
- **Webhook:** disponível (confirmar escopo atual).
- **Exportação manual:** FIT/TCX/GPX.
- **Risco:** Médio.
- **Estratégia inicial:** Avaliar após Strava; bom complemento OAuth2 para usuários Wahoo. Ponte via Strava no curto prazo.

### 2.3 Hammerhead Karoo

- **API oficial?** **Sem API aberta** para terceiros. O Karoo **sincroniza com Strava, TrainingPeaks, Komoot** e outros.
- **Autenticação:** N/A.
- **Dados:** disponíveis indiretamente via plataformas para as quais o Karoo faz sync.
- **Webhook:** Não.
- **Exportação manual:** FIT/TCX/GPX (e sync automático para terceiros).
- **Risco:** N/A (integração indireta).
- **Estratégia inicial:** **Integração indireta** via Strava/TrainingPeaks ou upload de FIT.

### 2.4 Polar

- **API oficial?** Sim — **Polar AccessLink API** (e Polar Open AccessLink), pública mediante registro de cliente.
- **SDK:** sem SDK amplo; API REST documentada.
- **Autenticação:** **OAuth2**.
- **Dados:** treinos/exercícios, dados físicos, atividade diária, sono, recovery (Nightly Recharge), dependendo de escopo.
- **Limites/custo:** rate limits definidos pela Polar (confirmar).
- **Webhook:** disponível (notificações de novos exercícios).
- **Exportação manual:** TCX/GPX/FIT via Polar Flow.
- **Risco:** Médio.
- **Estratégia inicial:** Adicionar após o núcleo (Strava/Intervals); OAuth2 viável.

### 2.5 Coros

- **API oficial?** Sim — **Coros Partner/Training API** (acesso via parceria/registro de desenvolvedor).
- **Autenticação:** **OAuth2** (programa de parceiro).
- **Dados:** atividades, dados de treino e métricas; escopo conforme parceria.
- **Limites/custo:** por parceria.
- **Webhook:** disponível para parceiros (confirmar).
- **Exportação manual:** FIT/TCX/GPX.
- **Risco:** Médio (depende de aprovação de parceria).
- **Estratégia inicial:** Adiar; ponte via Strava no curto prazo.

### 2.6 Suunto

- **API oficial?** Sim — **Suunto API** (programa de desenvolvedor / SuuntoPlus / antiga Movescount herança).
- **Autenticação:** **OAuth2**.
- **Dados:** workouts/moves, FC, GPS, métricas de atividade.
- **Limites/custo:** definidos pela Suunto (confirmar).
- **Webhook:** disponível (confirmar escopo).
- **Exportação manual:** FIT/GPX/TCX.
- **Risco:** Médio.
- **Estratégia inicial:** Adiar; ponte via Strava no curto prazo.

---

## 3. Saúde e Recuperação

### 3.1 Oura Ring

- **API oficial?** Sim — **Oura API v2**, documentação pública e madura.
- **SDK:** sem SDK oficial amplo; API REST limpa.
- **Autenticação:** **OAuth2** e **Personal Access Tokens** (para uso individual/desenvolvimento).
- **Dados:** sono, readiness, atividade diária, HRV, FC repouso, temperatura corporal, SpO2.
- **Limites/custo:** rate limits razoáveis; uso gratuito para acesso pessoal (confirmar termos comerciais).
- **Webhook:** suportado (notificações de novos dados).
- **Exportação manual:** export de dados via app/conta; primário é API.
- **Risco:** Baixo-Médio (API estável e bem documentada).
- **Estratégia inicial:** **Forte candidata para o módulo de recuperação** (após o núcleo de treino). OAuth2 + tokens pessoais facilitam o piloto.

### 3.2 Whoop

- **API oficial?** Sim — **Whoop API** oficial, documentada.
- **Autenticação:** **OAuth2**.
- **Dados:** recovery, strain, sono, HRV, FC repouso, ciclos.
- **Limites/custo:** rate limits definidos pela Whoop (confirmar); requer registro de app.
- **Webhook:** **Sim**, suportado (eventos de novos dados).
- **Exportação manual:** export via conta/app; primário é API.
- **Risco:** Baixo-Médio.
- **Estratégia inicial:** **Forte candidata para o módulo de recuperação**, junto com Oura. OAuth2 + webhooks.

### 3.3 Apple Health

- **API oficial?** **Não há API de nuvem.** Apenas **HealthKit on-device** (no iOS). Requer um **app iOS nativo** para ler/escrever dados.
- **Autenticação:** Permissões do usuário no dispositivo (não OAuth de nuvem).
- **Dados:** treinos, FC, HRV, sono, passos, VO2max etc. — **somente no dispositivo**.
- **Limites/custo:** N/A (framework do SO).
- **Webhook:** Não (modelo on-device com observers locais no app).
- **Exportação manual:** export de "Health Data" (arquivo XML/ZIP) pelo usuário a partir do app Saúde.
- **Risco:** N/A (depende de ter app iOS).
- **Estratégia inicial:** **Sem integração de backend possível diretamente.** Opções: (a) app iOS companheiro que envia dados ao backend; (b) importar o export XML do usuário; (c) **adiar** até existir app móvel.

### 3.4 Google Health Connect

- **API oficial?** **API on-device no Android** (Health Connect substitui a Google Fit API legada). Requer **app Android**.
- **Autenticação:** Permissões do usuário no dispositivo.
- **Dados:** atividades, FC, sono, passos, etc., agregando dados de outros apps de saúde no Android.
- **Limites/custo:** N/A (framework do SO).
- **Webhook:** Não (modelo on-device).
- **Exportação manual:** depende do app fonte.
- **Risco:** N/A (depende de ter app Android).
- **Estratégia inicial:** Análoga ao Apple Health — **requer app Android**; **adiar** até existir app móvel.

### 3.5 Fitbit

- **API oficial?** Sim — **Fitbit Web API** oficial, pública mediante registro de app.
- **Autenticação:** **OAuth2** (PKCE).
- **Dados:** atividade, FC, sono, passos, peso; (dados intradiários podem exigir aprovação adicional).
- **Limites/custo:** **rate limits** por usuário (ex.: 150 req/hora por usuário, padrão histórico — confirmar); gratuito mediante termos.
- **Webhook:** **Subscriptions** (notificações de atualização).
- **Exportação manual:** export de dados via conta.
- **Risco:** Médio (mudanças de termos sob a Google; dados intradiários restritos).
- **Estratégia inicial:** Opcional no módulo de recuperação; menor prioridade que Oura/Whoop para o público ciclista/endurance.

---

## 4. Matriz Comparativa

| Plataforma | Tipo de dado | API oficial | OAuth | Webhook | Formatos de exportação | Facilidade de integração | Risco de bloqueio | Custo | Prioridade MVP | Estratégia recomendada |
|------------|--------------|-------------|-------|---------|------------------------|--------------------------|-------------------|-------|----------------|------------------------|
| **Strava** | Treino/atividade | Pública | OAuth2 | Sim | FIT/TCX/GPX | Média-Alta | Médio-Alto | Gratuito (rate limits) | **Alta (P2)** | Primeira integração OAuth2; cuidar de branding e cláusulas de dados |
| **Garmin Connect** | Treino + saúde | Restrita (parceria) | OAuth1.0a | Sim (parceiro) | FIT/TCX/GPX | Baixa | Alto | Por contrato | Baixa (P5) | Adiar; usar FIT manual ou ponte Strava |
| **TrainingPeaks** | Treino/planos/carga | Restrita (parceria) | OAuth2 | Sim (parceiro) | CSV/FIT/TCX/GPX | Baixa-Média | Médio-Alto | Por contrato | **Alta via CSV (P1)** / API (P5) | Importar CSV exportado agora; API por parceria depois |
| **WKO5** | Análise (desktop) | Inexistente | — | Não | FIT/TCX/GPX/CSV | N/A (arquivos) | Muito baixo | Licença | Nenhuma | Tratar via arquivos / TrainingPeaks |
| **Intervals.icu** | Treino + wellness/carga | Pública | API key + OAuth2 | Verificar | FIT/TCX/GPX/JSON | Alta | Baixo | Gratuito/generoso | **Alta (P3)** | Integração precoce; ótima fonte de carga/wellness |
| **TrainerRoad** | Treino estruturado | Inexistente (pública) | — | Não | FIT/TCX | N/A | N/A | — | Nenhuma (indireta) | Indireto via Strava/TrainingPeaks |
| **Today's Plan** | Treino/planos | Restrita (parceria) | OAuth2 | Verificar | FIT/TCX/GPX/CSV | Baixa | Médio | Por contrato | Baixa | Adiar; via arquivos |
| **Golden Cheetah** | Treino (local) | Local/Open-source | — | Não | FIT/TCX/GPX/CSV/JSON | Alta (arquivos) | Muito baixo | Gratuito (GPL) | Média (arquivos) | Import/export de arquivos abertos |
| **Garmin (device)** | Atividade/wellness | Via Garmin Connect | OAuth | Sim (parceiro) | FIT/TCX/GPX | Baixa (Connect) / Alta (FIT local) | Alto | Por contrato | Média via FIT | FIT SDK + upload manual; ponte Strava |
| **Wahoo** | Treino/atividade | Pública (parceiro) | OAuth2 | Sim | FIT/TCX/GPX | Média | Médio | Por app/parceria | Média (P4+) | Após Strava; OAuth2 ou ponte Strava |
| **Hammerhead Karoo** | Atividade | Inexistente (aberta) | — | Não | FIT/TCX/GPX | N/A | N/A | — | Nenhuma (indireta) | Indireto via Strava/TrainingPeaks |
| **Polar** | Treino + recovery/sono | Pública (AccessLink) | OAuth2 | Sim | TCX/GPX/FIT | Média | Médio | Rate limits | Média (P4+) | Após núcleo; OAuth2 viável |
| **Coros** | Treino/atividade | Pública (parceiro) | OAuth2 | Sim (parceiro) | FIT/TCX/GPX | Baixa-Média | Médio | Por parceria | Baixa | Adiar; ponte Strava |
| **Suunto** | Treino/atividade | Pública (dev program) | OAuth2 | Sim | FIT/GPX/TCX | Média | Médio | Confirmar | Baixa | Adiar; ponte Strava |
| **Oura Ring** | Saúde/recuperação | Pública (v2) | OAuth2 + PAT | Sim | API/export | Alta | Baixo-Médio | Gratuito (pessoal) | **Média-Alta (P4)** | Módulo de recuperação |
| **Whoop** | Saúde/recuperação | Pública | OAuth2 | Sim | API/export | Alta | Baixo-Médio | Confirmar | **Média-Alta (P4)** | Módulo de recuperação |
| **Apple Health** | Saúde | Inexistente (cloud) | — (on-device) | Não | XML/ZIP export | Baixa (exige app iOS) | N/A | Gratuito | Baixa (sem app) | Adiar até app iOS; ou importar export XML |
| **Google Health Connect** | Saúde | On-device (Android) | — (on-device) | Não | Depende da fonte | Baixa (exige app Android) | N/A | Gratuito | Baixa (sem app) | Adiar até app Android |
| **Fitbit** | Saúde/recuperação | Pública (Web API) | OAuth2 (PKCE) | Sim (subscriptions) | Export via conta | Média-Alta | Médio | Gratuito (rate limits) | Baixa-Média | Opcional no módulo de recuperação |

> Legenda de prioridade: **P1** = primeira onda (arquivos/CSV) · **P2** = Strava OAuth · **P3** = Intervals.icu · **P4** = recuperação (Oura/Whoop) · **P5** = parcerias (Garmin/TrainingPeaks API) posteriores.

---

## 5. Estratégias para APIs Restritas ou Inexistentes

Para plataformas sem API pública, com API restrita por parceria, ou on-device, adote uma ou mais das abordagens abaixo:

1. **Upload manual de arquivos (base universal):**
   Aceite **FIT, TCX, GPX, CSV e JSON**. O formato **FIT** é o padrão de fato em ciclismo/endurance (Garmin, Wahoo, Coros etc.). Implemente um parser FIT robusto (ex.: FIT SDK) e normalize tudo para um modelo de dados interno. Esta é a forma mais resiliente e independente de fornecedor.

2. **Pasta de sincronização monitorada (watch folder):**
   Permita que o usuário/treinador deposite arquivos exportados em uma pasta (ou faça upload em lote); o sistema processa automaticamente. Útil para TrainingPeaks (CSV), Golden Cheetah, WKO5 e exports de dispositivos.

3. **Exportar-importar (export-import assistido):**
   Forneça instruções guiadas para o usuário exportar dados da plataforma de origem (ex.: Bulk Export do Strava, export XML do Apple Health, CSV do TrainingPeaks) e importar no Hub.

4. **Conectores de terceiros / pontes:**
   Use plataformas que já agregam sync como **ponte**. Exemplos: Strava recebe dados de Garmin, Wahoo, Karoo, Polar, Coros, Suunto, TrainerRoad — integrar Strava cobre indiretamente muitos dispositivos. Avaliar também serviços de sincronização especializados quando alinhados aos termos de cada plataforma.

5. **Integração diferida (deferred):**
   Para Garmin Connect API, TrainingPeaks API, Today's Plan, Coros e Suunto, **adie** a integração direta até haver: (a) volume de usuários que justifique o esforço de parceria; (b) aprovação formal no programa de desenvolvedor; (c) revisão jurídica dos contratos de API.

6. **App móvel companheiro (para saúde on-device):**
   Apple Health (HealthKit) e Google Health Connect **só** são acessíveis por um app nativo no dispositivo. Planeje um app iOS/Android que leia esses dados (com consentimento) e os envie ao backend. Até lá, ofereça importação do arquivo de export.

---

## 6. Roadmap Recomendado de Integração para o MVP

Ordem recomendada, do menor para o maior atrito/risco, maximizando cobertura de dados cedo:

### Fase 1 — Fundação por arquivos (P1)
- **Upload manual de FIT/TCX/GPX/CSV** com parser FIT robusto e modelo de dados normalizado.
- **Importação de CSV/export do TrainingPeaks** (workouts, métricas de carga PMC).
- Cobre indiretamente: Garmin, Wahoo, WKO5, Golden Cheetah, TrainerRoad, Karoo, Today's Plan.
- **Por quê primeiro:** zero dependência de aprovação, resiliente a mudanças unilaterais, entrega valor imediato.

### Fase 2 — Strava OAuth2 (P2)
- Implementar **OAuth2 + leitura de atividades + webhooks (push subscriptions)**.
- Atenção rigorosa a **branding** e às **cláusulas de armazenamento/agregação/bulk**.
- **Por quê:** maior alcance de usuários e ponte indireta para múltiplos dispositivos.

### Fase 3 — Intervals.icu (P3)
- Integrar via **API key/OAuth2**; ingerir atividades + **wellness** (HRV, sono, FC repouso) + **carga (Fitness/Fatigue/Form)**.
- **Por quê:** API aberta, baixo risco, dados de carga e recuperação consolidados com pouco esforço.

### Fase 4 — Recuperação: Oura e Whoop (P4)
- **Oura API v2** (OAuth2/PAT) e **Whoop API** (OAuth2 + webhooks) para o módulo de prontidão/recuperação.
- Opcional: **Polar** e **Fitbit** conforme demanda.
- **Por quê:** enriquece o modelo de treino com readiness/HRV/sono; APIs estáveis e bem documentadas.

### Fase 5 — Parcerias de API (P5) e apps móveis
- Buscar **parceria oficial** com **Garmin Connect** e **TrainingPeaks** (API completa), além de **Wahoo/Coros/Suunto** conforme base de usuários.
- Desenvolver **app móvel** para **Apple Health (HealthKit)** e **Google Health Connect**.
- **Por quê:** maior esforço, aprovação e custo; justifica-se com escala e revisão jurídica dos contratos.

---

### Princípios transversais

- **Normalizar tudo** para um modelo de dados interno único (independente da fonte).
- **Registrar a proveniência** de cada dado (fonte, timestamp de ingestão, ID externo) para deduplicação e auditoria.
- **Respeitar termos comerciais e de marca** de cada plataforma (especialmente Strava).
- **Reverificar a documentação oficial** de cada API imediatamente antes de implementar (ver disclaimer no topo).
- **Tratar webhooks de forma idempotente** e com tolerância a reentrega.

---

*Documento de referência interna — Athlete AI Training Hub. Reverifique sempre contra a documentação oficial vigente de cada plataforma antes da implementação.*
