"""Curated training-knowledge documents + chunking for the knowledge base.

This content is GENERAL training methodology, kept strictly separate from any
athlete's real data. It seeds the global knowledge base used as conceptual
reference by the AI layer (athlete_id IS NULL on its embeddings).

Reference only — never replaces medical or professional evaluation.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeDoc:
    title: str
    category: str
    content: str
    source: str = "internal_methodology"


CURATED_DOCUMENTS: list[KnowledgeDoc] = [
    KnowledgeDoc(
        "Periodização clássica e reversa", "periodization",
        "A periodização clássica progride de alto volume e baixa intensidade (base) "
        "para menor volume e maior intensidade (build/peak), organizada em macro, meso "
        "e microciclos. A periodização reversa inverte a ênfase, começando pela "
        "intensidade quando a base aeróbica já está estabelecida ou quando a janela até "
        "a prova é curta. A escolha depende do calendário, do histórico e do estado de "
        "forma atual do atleta.",
    ),
    KnowledgeDoc(
        "Distribuição de intensidade: polarized, pyramidal, sweet spot", "intensity_distribution",
        "Polarized (~80% em Z1-Z2, ~20% em Z4-Z5, pouco threshold) favorece grande "
        "volume aeróbico com blocos de alta intensidade. Pyramidal concentra a maior "
        "parte em baixa intensidade com proporção decrescente em tempo/threshold/VO2. "
        "Sweet spot (88-94% do FTP) maximiza estímulo de threshold por unidade de tempo, "
        "útil quando o tempo é limitado, mas acumula fadiga e monotonia se usado em "
        "excesso. A distribuição deve respeitar a fase do bloco e a tolerância individual.",
    ),
    KnowledgeDoc(
        "Zonas de treino e objetivos fisiológicos", "zones",
        "Z2 (endurance) desenvolve base aeróbica, oxidação de gordura e densidade "
        "mitocondrial. Tempo/sweet spot eleva o limiar. Threshold (Z4, ~FTP) melhora o "
        "lactate threshold. VO2max (Z5, 3-8 min) eleva o consumo máximo de oxigênio. "
        "Capacidade anaeróbica (30s-2min) e sprint/neuromuscular (<15s) desenvolvem "
        "potência de pico e tolerância ao lactato. Cada zona pede recuperação compatível.",
    ),
    KnowledgeDoc(
        "Sobrecarga, recuperação, supercompensação e tapering", "load_recovery",
        "O treino gera fadiga; a adaptação ocorre na recuperação (supercompensação). "
        "Sobrecarga progressiva exige incrementos graduais — regra prática de no máximo "
        "~10% de aumento de carga por semana. O tapering reduz volume (mantendo alguma "
        "intensidade) por 1-3 semanas antes de uma prova alvo para dissipar fadiga (ATL) "
        "preservando forma (CTL), elevando o TSB. Ignorar sono, HRV e fadiga subjetiva "
        "aumenta risco de overreaching não funcional e lesão.",
    ),
    KnowledgeDoc(
        "CTL, ATL, TSB e o Performance Manager", "load_metrics",
        "CTL (carga crônica, constante ~42 dias) aproxima a forma/fitness. ATL (carga "
        "aguda, ~7 dias) aproxima a fadiga. TSB = CTL_ontem - ATL_ontem aproxima a "
        "prontidão/forma: muito negativo indica fadiga acumulada; levemente positivo é "
        "comum em pico de prova. Ramp rate (variação de CTL por semana) muito alto "
        "sinaliza progressão agressiva. Monotonia (Foster) alta e strain elevado "
        "associam-se a maior risco.",
    ),
    KnowledgeDoc(
        "FTP, Critical Power, W' e Power Duration Curve", "power_models",
        "FTP aproxima a maior potência sustentável em estado estável (~1h). Critical "
        "Power (CP) é a assíntota da relação potência-duração; W' é a capacidade de "
        "trabalho acima de CP (reserva anaeróbica). A Power Duration Curve (melhores "
        "potências por duração: 5s, 1min, 5min, 20min, 60min) caracteriza o perfil do "
        "atleta (sprinter, all-rounder, diesel) e orienta a especificidade do treino.",
    ),
    KnowledgeDoc(
        "Decoupling aeróbico e eficiência", "aerobic_efficiency",
        "O decoupling aeróbico (Pw:Hr) mede a deriva entre potência e frequência "
        "cardíaca ao longo de um esforço prolongado; valores baixos (<5%) indicam boa "
        "durabilidade aeróbica. A eficiência aeróbica melhora com volume em Z2 "
        "consistente. São indicadores úteis de progressão da base sem depender de testes "
        "máximos.",
    ),
    KnowledgeDoc(
        "Especificidades de MTB: XCO, XCM e maratona", "mtb_specificity",
        "MTB XCO é curto e altamente variável (surtos repetidos acima do threshold, "
        "demanda neuromuscular e técnica); pede capacidade anaeróbica e VO2max robustos, "
        "além de repetibilidade de sprints. XCM/maratona é longo e exige durabilidade "
        "aeróbica, economia, gestão de nutrição e resistência à fadiga. O treino deve "
        "espelhar a estrutura de demanda da prova alvo (race specificity).",
    ),
    KnowledgeDoc(
        "Gran fondo, estrada e stage racing", "road_specificity",
        "Gran fondo e provas de estrada longas enfatizam threshold sustentado, "
        "durabilidade e eficiência. Stage racing acrescenta a recuperação dia a dia e a "
        "gestão de carga acumulada ao longo de múltiplas etapas, exigindo CTL alto e "
        "estratégia de fadiga.",
    ),
    KnowledgeDoc(
        "Adaptação ao calor e à altitude", "environmental_adaptation",
        "A aclimatação ao calor (sessões controladas em ambiente quente por ~1-2 "
        "semanas) aumenta o volume plasmático e melhora a termorregulação. A adaptação à "
        "altitude (live high/train low ou blocos em altitude) pode elevar a massa de "
        "hemoglobina, com resposta individual variável e necessidade de gestão cuidadosa "
        "de carga e recuperação.",
    ),
    KnowledgeDoc(
        "Strength endurance para ciclismo", "strength",
        "Trabalho de força (academia e/ou intervalos de baixa cadência e alto torque) "
        "complementa a resistência, melhora a economia e a robustez musculoesquelética e "
        "pode beneficiar a potência de pico. Deve ser periodizado para não competir com "
        "as sessões-chave de alta intensidade nem comprometer a recuperação.",
    ),
    KnowledgeDoc(
        "Tapering: princípios práticos", "tapering",
        "Um taper eficaz costuma reduzir o volume em 40-60% mantendo curtos estímulos de "
        "intensidade para preservar a prontidão neuromuscular, ao longo de 7-21 dias "
        "conforme o CTL e a duração da prova. O objetivo é maximizar o TSB no dia da "
        "prova sem perder fitness. A resposta ao taper é individual — o histórico do "
        "atleta é a melhor referência.",
    ),
    KnowledgeDoc(
        "Planejamento de treino individualizado por IA (estudo de caso)",
        "ai_methodology_research",
        "Estudo de caso de planejamento de treino individualizado por IA para "
        "ciclistas de estrada modela a carga a partir do histórico do atleta (TSS, "
        "CTL/ATL, distribuição por zona) e ajusta a prescrição ao indivíduo em vez de "
        "um modelo único. Aproveitável para a Training Intelligence Layer: features "
        "derivadas do próprio histórico, validação contra resposta observada e "
        "personalização progressiva conforme mais dados chegam. É apoio à decisão "
        "baseado em dados, não substitui avaliação profissional.",
        source="https://www.mdpi.com/2076-3417/11/1/313",
    ),
    KnowledgeDoc(
        "Confiança e aceitação de planos de treino gerados por IA",
        "ai_trust",
        "A aceitação de planos gerados por IA por atletas recreativos depende de "
        "explicabilidade (mostrar por que cada treino foi sugerido), transparência "
        "sobre os dados e sinais usados, controle do usuário (poder ajustar/recusar), "
        "linguagem clara e não-prescritiva, e validação contra o histórico real. "
        "Recomendações devem expor os sinais (forma, bloco, metodologia) e permitir "
        "manter/ajustar a sugestão. Reforça a transição do treinador humano para a IA "
        "com continuidade respeitosa, sem prometer resultados.",
        source="https://pmc.ncbi.nlm.nih.gov/articles/PMC11908068/",
    ),
]


def chunk_text(text: str, max_chars: int = 600, overlap: int = 80) -> list[str]:
    """Split a document into overlapping chunks for embedding.

    Simple character-window chunking is sufficient for these short, self-contained
    concept documents; it keeps related sentences together with light overlap.
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = end - overlap
    return chunks
