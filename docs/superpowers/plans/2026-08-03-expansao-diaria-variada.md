# Expansão Diária Variada — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A expansão do plano gera semanas com forma real (longão no domingo, dias úteis ≤90 min, variantes de Z2 rotacionando) em vez de N cópias do mesmo treino, e resolve conflito entre planos ("prova mais próxima vence o dia").

**Architecture:** Biblioteca de templates cresce (6 novos em `templates.py`); `allocate_days` é reescrita com esqueleto semanal ancorado no dia da semana + distribuição de TSS com longão a 40% e teto diário, retornando `(days, tss_dropped)`; `expand_plan_to_daily` aplica a regra multi-plano na gravação e expõe `tss_dropped` na resposta.

**Tech Stack:** FastAPI + SQLAlchemy async, Pydantic (StructuredWorkout), pytest.

**Spec:** `docs/superpowers/specs/2026-08-03-expansao-diaria-variada-design.md`

## Global Constraints

- Backend NÃO roda no host — suíte na VM Contabo:
  `tar -cz -C /c/projetos/treinador-ciclismo/backend . | ssh -i ~/.ssh/id_ed25519_aath_vps -o IdentitiesOnly=yes root@62.171.128.103 "tar -xz -C /opt/aath-test/backend && docker run --rm -v /opt/aath-test/backend:/app -w /app aath-test:latest timeout 900 pytest -q 2>&1 | tail -15"`
  (verificação estática dos passos "verify it fails" quando indicado; suíte real nas Tasks conforme marcado).
- Branch: `feat/expansao-diaria-variada` (existe, tem a spec).
- Semana é seg→dom (`week_start` = segunda). Descansos na ordem seg, sex, sáb.
- Longão: domingo, 40% do TSS semanal (PEAK 30%), duração 2h-5h.
- Teto dias úteis 90 min; "Z2 curto" (sáb) ≤75 min.
- Sem migração de banco; sem mudança de UI.

---

### Task 1: Templates novos em `templates.py`

**Files:**
- Modify: `backend/app/services/workout/templates.py` (append após `openers`, antes de `TEMPLATES`)
- Test: `backend/app/tests/test_workout/test_templates_novos.py` (novo)

**Interfaces:**
- Consumes: `Step`, `Repeat`, `StructuredWorkout`, `_pwr`, `_cooldown_target` (já no arquivo).
- Produces (Task 2 depende): `tempo(ftp)`, `forca_cadencia(ftp)`, `z2_sprints(ftp)`, `z2_progressivo(ftp)`, `long_ride(ftp, duration_s=10800)`, `long_ride_tempo(ftp, duration_s=10800)` — todas retornam `StructuredWorkout`.

- [ ] **Step 1: Write the failing tests**

```python
"""Templates novos da expansão variada (spec 2026-08-03)."""
from app.services.workout import analysis, templates


def test_tempo_2x20():
    w = templates.tempo(250.0)
    assert w.name == "Tempo 2x20"
    assert 3300 <= analysis.total_duration_s(w) <= 4500
    assert 45 <= analysis.estimated_tss(w) <= 75


def test_forca_cadencia_tem_cadencia_baixa():
    w = templates.forca_cadencia(250.0)
    reps = [el for el in w.elements if hasattr(el, "count")]
    assert len(reps) == 1
    on = reps[0].steps[0]
    assert on.cadence_low == 50 and on.cadence_high == 60
    assert 40 <= analysis.estimated_tss(w) <= 70


def test_z2_sprints_dentro_do_teto_de_90min():
    w = templates.z2_sprints(250.0)
    assert analysis.total_duration_s(w) <= 90 * 60
    assert 40 <= analysis.estimated_tss(w) <= 75


def test_z2_progressivo_sobe_ate_topo_da_zona():
    w = templates.z2_progressivo(250.0)
    assert analysis.total_duration_s(w) <= 90 * 60
    actives = [el for el in w.elements if getattr(el, "intensity", None) == "active"]
    assert actives[-1].target.high == 0.75


def test_long_ride_escala_por_duracao():
    w3 = templates.long_ride(250.0, duration_s=3 * 3600)
    w5 = templates.long_ride(250.0, duration_s=5 * 3600)
    assert analysis.total_duration_s(w3) == 3 * 3600
    assert analysis.total_duration_s(w5) == 5 * 3600
    assert analysis.estimated_tss(w5) > analysis.estimated_tss(w3)


def test_long_ride_tempo_tem_3_blocos_e_duracao_pedida():
    w = templates.long_ride_tempo(250.0, duration_s=4 * 3600)
    assert analysis.total_duration_s(w) == 4 * 3600
    reps = [el for el in w.elements if hasattr(el, "count")]
    assert len(reps) == 1 and reps[0].count == 3


def test_templates_serializaveis():
    for w in (templates.tempo(200.0), templates.forca_cadencia(200.0),
              templates.z2_sprints(200.0), templates.z2_progressivo(200.0),
              templates.long_ride(200.0), templates.long_ride_tempo(200.0)):
        d = w.model_dump()
        assert d["name"] and d["elements"]
```

- [ ] **Step 2: Verify it fails** — estático: nenhuma das 6 funções existe em `templates.py` ⇒ `AttributeError` na coleta.

- [ ] **Step 3: Write minimal implementation** (append em `templates.py`, antes de `TEMPLATES`):

```python
def tempo(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Tempo 2x20",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.65)),
            Repeat(count=2, steps=[
                Step(intensity="active", duration_s=1200, target=_pwr(0.76, 0.85)),
                Step(intensity="rest", duration_s=300, target=_pwr(0.50, 0.55)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def forca_cadencia(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Força 4x8 (50-60 rpm)",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.65)),
            Repeat(count=4, steps=[
                Step(intensity="active", duration_s=480, target=_pwr(0.75, 0.85),
                     cadence_low=50, cadence_high=60,
                     note="Sentado, cadência 50-60 rpm"),
                Step(intensity="rest", duration_s=300, target=_pwr(0.50, 0.55)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def z2_sprints(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Z2 + 6 sprints",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.60)),
            Step(intensity="active", duration_s=1800, target=_pwr(0.62, 0.68)),
            Repeat(count=6, steps=[
                Step(intensity="active", duration_s=10, target=_pwr(1.50, 2.00),
                     note="Sprint sentado, cadência máxima"),
                Step(intensity="rest", duration_s=290, target=_pwr(0.60, 0.65)),
            ]),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def z2_progressivo(ftp_watts: float) -> StructuredWorkout:
    return StructuredWorkout(
        name="Z2 progressivo",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.60)),
            Step(intensity="active", duration_s=1200, target=_pwr(0.60, 0.65)),
            Step(intensity="active", duration_s=1200, target=_pwr(0.65, 0.70)),
            Step(intensity="active", duration_s=1200, target=_pwr(0.70, 0.75)),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def long_ride(ftp_watts: float, duration_s: int = 10800) -> StructuredWorkout:
    active = max(3600, duration_s - 1200)
    return StructuredWorkout(
        name="Longão Z2",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.60)),
            Step(intensity="active", duration_s=active, target=_pwr(0.62, 0.68)),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )


def long_ride_tempo(ftp_watts: float, duration_s: int = 10800) -> StructuredWorkout:
    # 3 blocos de 15min Z3 com 5min Z2 entre eles; o resto é Z2 puro.
    tempo_total = 3 * 900 + 3 * 300
    z2 = max(1800, duration_s - 1200 - tempo_total)
    return StructuredWorkout(
        name="Longão com tempo 3x15",
        elements=[
            Step(intensity="warmup", duration_s=600, target=_pwr(0.55, 0.60)),
            Step(intensity="active", duration_s=z2 // 2, target=_pwr(0.62, 0.68)),
            Repeat(count=3, steps=[
                Step(intensity="active", duration_s=900, target=_pwr(0.78, 0.84)),
                Step(intensity="rest", duration_s=300, target=_pwr(0.62, 0.68)),
            ]),
            Step(intensity="active", duration_s=z2 - z2 // 2, target=_pwr(0.62, 0.68)),
            Step(intensity="cooldown", duration_s=600, target=_cooldown_target()),
        ],
    )
```

Nota de consistência: `long_ride(ftp, d)` tem total exato `d` quando `d ≥ 4800`
(active = d − 1200); `long_ride_tempo` idem quando `d ≥ 3h` — os testes usam 3h,
4h e 5h, então a igualdade exata vale.

- [ ] **Step 4: Verify** — leitura confere; suíte roda na VM na Task 4.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/workout/templates.py backend/app/tests/test_workout/test_templates_novos.py
git commit -m "feat(workout): 6 templates novos (longão, tempo, força, variantes Z2)"
```

---

### Task 2: `allocate_days` v2 — esqueleto semanal + distribuição de TSS

**Files:**
- Modify: `backend/app/services/planning/plan_expander.py` (substituir `_ROLE_*`, `_QUALITY_BY_BLOCK`, `_scaled_endurance` e `allocate_days`; manter `WeekSpec`, `DailyPlanned`, `_daily_from`)
- Test: `backend/app/tests/test_planning/test_plan_expander.py` (REESCREVER o arquivo)

**Interfaces:**
- Consumes: templates da Task 1; `analysis.estimated_tss/intensity_factor/total_duration_s`.
- Produces (Task 3 depende): `allocate_days(weeks, ftp, race_date, rest_per_week, today, blocked_days=frozenset()) -> tuple[list[DailyPlanned], float]` — o segundo item é `tss_dropped` (≥0.0).

- [ ] **Step 1: Write the failing tests** (substituir todo o conteúdo de `test_plan_expander.py`):

```python
"""allocate_days v2: esqueleto semanal + distribuição de TSS (spec 2026-08-03)."""
from datetime import date

from app.models.enums import BlockType, WorkoutType
from app.services.planning.plan_expander import WeekSpec, allocate_days

FTP = 250.0
MON = date(2026, 1, 5)  # segunda-feira
RACE_FAR = date(2026, 12, 31)


def _base_week(tss=650.0):
    return WeekSpec(MON, BlockType.BASE, tss, False)


def test_longao_no_domingo_com_40pct():
    days, _ = allocate_days([_base_week()], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    sunday = [d for d in days if d.planned_date.weekday() == 6]
    assert len(sunday) == 1
    assert "Longão" in sunday[0].structure["name"]
    assert sunday[0].planned_tss >= 0.30 * 650  # ~40% com tolerância de clamp
    assert 2 * 3600 <= sunday[0].planned_duration_s <= 5 * 3600


def test_teto_de_90min_nos_dias_uteis():
    days, _ = allocate_days([_base_week(tss=900.0)], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    for d in days:
        if d.planned_date.weekday() != 6:  # tudo menos o longão
            assert d.planned_duration_s <= 90 * 60


def test_descansos_seg_sex_sab_com_rest_3():
    days, _ = allocate_days([_base_week()], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=3, today=MON)
    weekdays = {d.planned_date.weekday() for d in days}
    assert 0 not in weekdays and 4 not in weekdays and 5 not in weekdays
    assert 6 in weekdays  # longão sobrevive


def test_rotacao_de_variantes_entre_semanas():
    weeks = [WeekSpec(MON, BlockType.BASE, 650.0, False),
             WeekSpec(date(2026, 1, 12), BlockType.BASE, 700.0, False),
             WeekSpec(date(2026, 1, 19), BlockType.BASE, 750.0, False)]
    days, _ = allocate_days(weeks, ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    quartas = sorted((d for d in days if d.planned_date.weekday() == 2),
                     key=lambda d: d.planned_date)
    names = [q.structure["name"] for q in quartas]
    assert len(set(names)) == 3  # variantes diferentes nas 3 semanas


def test_base_tem_sweet_spot_e_forca():
    days, _ = allocate_days([_base_week()], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    by_wd = {d.planned_date.weekday(): d for d in days}
    assert by_wd[1].workout_type == WorkoutType.SWEET_SPOT
    assert "Força" in by_wd[3].structure["name"]


def test_build_tem_vo2_tempo_e_longao_com_tempo():
    wk = WeekSpec(MON, BlockType.BUILD, 700.0, False)
    days, _ = allocate_days([wk], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    by_wd = {d.planned_date.weekday(): d for d in days}
    assert by_wd[1].workout_type == WorkoutType.VO2MAX
    assert by_wd[3].workout_type == WorkoutType.TEMPO
    assert "tempo" in by_wd[6].structure["name"].lower()


def test_deload_sem_longao():
    wk = WeekSpec(MON, BlockType.RECOVERY, 400.0, True)
    days, _ = allocate_days([wk], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    for d in days:
        assert d.planned_duration_s <= 90 * 60
        assert "Longão" not in d.structure["name"]


def test_rampa_semanal_preservada():
    # TSS moderados para nada saturar nos tetos (longão < 5h nas duas semanas).
    weeks = [WeekSpec(MON, BlockType.BASE, 450.0, False),
             WeekSpec(date(2026, 1, 12), BlockType.BASE, 495.0, False)]
    days, _ = allocate_days(weeks, ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    w1 = sum(d.planned_tss for d in days if d.planned_date < date(2026, 1, 12))
    w2 = sum(d.planned_tss for d in days if d.planned_date >= date(2026, 1, 12))
    assert w2 > w1


def test_tss_dropped_reportado_quando_nao_cabe():
    days, dropped = allocate_days([_base_week(tss=2000.0)], ftp=FTP,
                                  race_date=RACE_FAR, rest_per_week=1, today=MON)
    assert dropped > 0
    delivered = sum(d.planned_tss for d in days)
    assert delivered + dropped >= 2000.0 * 0.95


def test_semana_da_prova_openers_2_dias_antes():
    race = date(2026, 1, 10)  # sábado da semana
    wk = WeekSpec(MON, BlockType.TAPER, 250.0, False)
    days, _ = allocate_days([wk], ftp=FTP, race_date=race,
                            rest_per_week=1, today=MON)
    by_date = {d.planned_date: d for d in days}
    assert date(2026, 1, 8) in by_date  # qui = prova - 2
    assert "Openers" in by_date[date(2026, 1, 8)].structure["name"]
    assert all(d.planned_date <= race for d in days)


def test_dias_bloqueados_continuam_pulados():
    blocked = frozenset({date(2026, 1, 7), date(2026, 1, 8)})
    days, _ = allocate_days([_base_week()], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON, blocked_days=blocked)
    assert {d.planned_date for d in days}.isdisjoint(blocked)


def test_janela_respeita_today_e_race():
    days, _ = allocate_days([_base_week()], ftp=FTP, race_date=date(2026, 1, 9),
                            rest_per_week=1, today=date(2026, 1, 7))
    assert all(date(2026, 1, 7) <= d.planned_date <= date(2026, 1, 9) for d in days)
```

- [ ] **Step 2: Verify it fails** — estático: `allocate_days` atual retorna `list`, não tupla ⇒ o unpack `days, _ =` quebra em todos os testes; esqueleto/nomes também não existem.

- [ ] **Step 3: Write minimal implementation** — substituir em `plan_expander.py` o miolo (de `_ROLE_ENDURANCE` até o fim de `allocate_days`) por:

```python
# ---- Esqueleto semanal (spec 2026-08-03) ------------------------------------
# Papéis por dia da semana (0=seg .. 6=dom). Descansos na ordem seg, sex, sáb.
_REST_ORDER = (0, 4, 5)

_SKELETON: dict[BlockType, dict[int, str]] = {
    BlockType.BASE:     {1: "q1", 2: "z2var", 3: "q2", 4: "easy", 5: "short_z2", 6: "long"},
    BlockType.BUILD:    {1: "q1", 2: "z2var", 3: "q2", 4: "easy", 5: "short_z2", 6: "long"},
    BlockType.PEAK:     {1: "q1", 2: "z2var", 3: "q2", 4: "easy", 5: "easy", 6: "long"},
    BlockType.TAPER:    {2: "openers", 3: "short_z2", 4: "easy", 6: "short_z2"},
    BlockType.RECOVERY: {1: "easy", 2: "easy_z2", 3: "easy", 5: "easy_z2", 6: "short_z2"},
}

_QUALITY: dict[BlockType, dict[str, tuple]] = {
    BlockType.BASE:  {"q1": (templates.sweet_spot, WorkoutType.SWEET_SPOT),
                      "q2": (templates.forca_cadencia, WorkoutType.TEMPO)},
    BlockType.BUILD: {"q1": (templates.vo2max, WorkoutType.VO2MAX),
                      "q2": (templates.tempo, WorkoutType.TEMPO)},
    BlockType.PEAK:  {"q1": (templates.vo2max, WorkoutType.VO2MAX),
                      "q2": (templates.vo2max, WorkoutType.VO2MAX)},
}

_Z2_ROTATION = (templates.z2_sprints, templates.z2_progressivo, templates.endurance)

_LONG_SHARE = {BlockType.BASE: 0.40, BlockType.BUILD: 0.40, BlockType.PEAK: 0.30}
_LONG_MIN_S = 2 * 3600
_LONG_MAX_S = 5 * 3600
_WEEKDAY_CAP_S = 90 * 60
_SHORT_Z2_CAP_S = 75 * 60


def _long_for_tss(block: BlockType, ftp: float, target_tss: float) -> StructuredWorkout:
    """Longão (Z2 puro; com tempo no BUILD) com duração dimensionada pelo TSS alvo."""
    fn = templates.long_ride_tempo if block == BlockType.BUILD else templates.long_ride
    probe = fn(ftp, _LONG_MIN_S)
    if_ = analysis.intensity_factor(probe)
    dur = _LONG_MIN_S if if_ <= 0 else int(target_tss / ((if_ ** 2) * 100) * 3600)
    dur = max(_LONG_MIN_S, min(_LONG_MAX_S, dur))
    return fn(ftp, dur)


def _scaled_endurance_capped(ftp: float, target_tss: float, cap_s: int) -> StructuredWorkout:
    """Endurance Z2 escalado ao TSS alvo, nunca passando de ``cap_s`` no total."""
    w = templates.endurance(ftp)
    base = analysis.estimated_tss(w)
    factor = 1.0 if base <= 0 or target_tss <= 0 else max(0.5, target_tss / base)
    for el in w.elements:
        if getattr(el, "intensity", None) == "active":
            el.duration_s = int(el.duration_s * factor)
    excess = analysis.total_duration_s(w) - cap_s
    if excess > 0:
        for el in w.elements:
            if getattr(el, "intensity", None) == "active":
                el.duration_s = max(600, el.duration_s - excess)
    return w


def allocate_days(
    weeks: list[WeekSpec], ftp: float, race_date: date, rest_per_week: int, today: date,
    blocked_days: frozenset[date] = frozenset(),
) -> tuple[list[DailyPlanned], float]:
    rest = max(1, min(3, rest_per_week))
    rest_days = set(_REST_ORDER[:rest])
    out: list[DailyPlanned] = []
    dropped_total = 0.0

    for i, wk in enumerate(weeks):
        visible = [wk.week_start + timedelta(days=j) for j in range(7)]
        visible = [d for d in visible if today <= d <= race_date and d not in blocked_days]
        if not visible:
            continue

        skel = _SKELETON.get(wk.block_type, _SKELETON[BlockType.BASE])
        roles: dict[date, str] = {}
        for d in visible:
            wd = d.weekday()
            if wd in rest_days:
                continue
            role = skel.get(wd)
            if role:
                roles[d] = role

        # Semana da prova: openers em prova-2; entre openers e prova, regenerativo.
        # O openers fixo do esqueleto TAPER (qua) vira Z2 curto para não duplicar.
        if wk.week_start <= race_date <= wk.week_start + timedelta(days=6):
            op = race_date - timedelta(days=2)
            for d in list(roles):
                if d >= op:
                    del roles[d]
                elif roles[d] == "openers":
                    roles[d] = "short_z2"
            if today <= op <= race_date and op not in blocked_days:
                roles[op] = "openers"
                mid = op + timedelta(days=1)
                if today <= mid < race_date and mid not in blocked_days:
                    roles[mid] = "easy"

        # 1) Dias de papel fixo.
        fixed: dict[date, tuple[StructuredWorkout, WorkoutType]] = {}
        long_day = next((d for d, r in roles.items() if r == "long"), None)
        short_days = [d for d, r in roles.items() if r == "short_z2"]
        for d, r in roles.items():
            if r in ("long", "short_z2"):
                continue
            if r in ("q1", "q2"):
                fn, wtype = _QUALITY[wk.block_type][r]
                fixed[d] = (fn(ftp), wtype)
            elif r == "openers":
                fixed[d] = (templates.openers(ftp), WorkoutType.VO2MAX)
            elif r == "easy":
                fixed[d] = (templates.recovery(ftp), WorkoutType.RECOVERY)
            elif r == "easy_z2":
                fixed[d] = (templates.endurance(ftp), WorkoutType.ENDURANCE)
            elif r == "z2var":
                fixed[d] = (_Z2_ROTATION[i % len(_Z2_ROTATION)](ftp), WorkoutType.ENDURANCE)
        fixed_tss = sum(analysis.estimated_tss(w) for w, _ in fixed.values())

        # 2) Longão (40% / 30% do TSS semanal) e Z2 curto absorvem o restante.
        loading = wk.block_type in _LONG_SHARE and not wk.is_recovery_week
        long_w: StructuredWorkout | None = None
        long_tss = 0.0
        if long_day is not None and loading:
            long_w = _long_for_tss(wk.block_type, ftp, wk.planned_tss * _LONG_SHARE[wk.block_type])
            long_tss = analysis.estimated_tss(long_w)
        short_w: StructuredWorkout | None = None
        if short_days:
            # O restante divide igual entre os dias de Z2 curto.
            target = 0.0
            if loading:
                target = max(0.0, wk.planned_tss - fixed_tss - long_tss) / len(short_days)
            short_w = _scaled_endurance_capped(ftp, target, _SHORT_Z2_CAP_S)

        # 3) Excedente volta ao longão (até 5h); o resto é descartado e reportado.
        if loading:
            short_tss = (analysis.estimated_tss(short_w) if short_w else 0.0) * len(short_days)
            leftover = wk.planned_tss - fixed_tss - long_tss - short_tss
            if leftover > 0 and long_w is not None:
                long_w = _long_for_tss(wk.block_type, ftp, long_tss + leftover)
                long_tss = analysis.estimated_tss(long_w)
                leftover = wk.planned_tss - fixed_tss - long_tss - short_tss
            dropped_total += max(0.0, leftover)

        for d in sorted(roles):
            if d == long_day and long_w is not None:
                out.append(_daily_from(d, _with_meta(long_w, ftp), WorkoutType.ENDURANCE))
            elif d in short_days and short_w is not None:
                out.append(_daily_from(d, _with_meta(short_w, ftp), WorkoutType.ENDURANCE))
            elif d in fixed:
                w, wtype = fixed[d]
                out.append(_daily_from(d, _with_meta(w, ftp), wtype))
    return out, round(dropped_total, 1)


def _with_meta(w: StructuredWorkout, ftp: float) -> StructuredWorkout:
    w.ftp_watts = ftp
    w.estimated_tss = analysis.estimated_tss(w)
    return w
```

Remover: `_ROLE_ENDURANCE/_ROLE_SWEET/_ROLE_VO2/_ROLE_RECOVERY/_ROLE_OPENERS`,
`_QUALITY_BY_BLOCK`, `_scaled_endurance`, `_make` (não usados mais). O import
de `WorkoutType` e `templates`/`analysis` já existe no arquivo. NÃO tocar em
`expand_plan_to_daily` nesta task — ela quebra (unpack) e é corrigida na Task 3;
rodar nesta task só `pytest app/tests/test_planning/test_plan_expander.py app/tests/test_workout/test_templates_novos.py`.

Caso TAPER com `long_day` (não existe no skeleton TAPER — dom é `short_z2`):
`loading=False` ⇒ dom vira Z2 curto de duração base, conforme spec.

- [ ] **Step 4: Verify** — estático + suíte parcial na VM (comando das Global Constraints trocando o final por `timeout 900 pytest -q app/tests/test_planning/test_plan_expander.py app/tests/test_workout/test_templates_novos.py`). Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/planning/plan_expander.py backend/app/tests/test_planning/test_plan_expander.py
git commit -m "feat(plans): esqueleto semanal com longão e distribuição de TSS na expansão"
```

---

### Task 3: `expand_plan_to_daily` — tupla, `tss_dropped`, regra multi-plano

**Files:**
- Modify: `backend/app/services/planning/plan_expander.py:194-220` (função `expand_plan_to_daily`)
- Test: `backend/app/tests/test_api/test_plan_expand_multiplano.py` (novo; fixtures copiadas de `test_plan_generate_replace.py`)

**Interfaces:**
- Consumes: `allocate_days(...) -> tuple[list[DailyPlanned], float]` (Task 2).
- Produces: resposta do expand ganha `"tss_dropped": float`; dias disputados seguem "prova mais próxima vence".

- [ ] **Step 1: Write the failing test** (arquivo novo — fixture `env` e `_auth` idênticas às de `backend/app/tests/test_api/test_plan_generate_replace.py`, copiar dali; só os testes abaixo mudam):

```python
"""Expand: regra multi-plano 'prova mais próxima vence' + tss_dropped (spec 2026-08-03)."""
from __future__ import annotations

from datetime import date, timedelta

# ... copiar imports, fixture `env` e helper `_auth` de test_plan_generate_replace.py ...
from sqlalchemy import select

from app.models.race import Race
from app.models.workout import WorkoutPlanned

pytestmark = pytest.mark.asyncio


async def _make_race(env, name: str, when: date) -> str:
    async with env.maker() as s:
        rc = Race(athlete_id=env.aid, name=name, race_date=when, priority="B")
        s.add(rc)
        await s.flush()
        rid = str(rc.id)
        await s.commit()
    return rid


async def _gen_and_expand(env, headers, name: str, race_iso: str, race_id: str) -> dict:
    r = await env.client.post("/api/v1/plans/generate", json={
        "name": name, "race_date": race_iso, "target_race_id": race_id, "priority": "B",
    }, headers=headers)
    assert r.status_code == 201, r.text
    plan_id = r.json()["id"]
    ex = await env.client.post(f"/api/v1/plans/{plan_id}/expand", headers=headers)
    assert ex.status_code == 201, ex.text
    return ex.json()


async def test_prova_mais_proxima_vence_o_dia(env):
    headers = await _auth(env.client)
    near_date = date.today() + timedelta(days=21)
    far_date = date.today() + timedelta(days=180)
    near = await _make_race(env, "Prova Perto", near_date)
    far = await _make_race(env, "Prova Longe", far_date)

    # Plano da prova distante primeiro, depois o da prova próxima.
    await _gen_and_expand(env, headers, "Plano Longe", far_date.isoformat(), far)
    await _gen_and_expand(env, headers, "Plano Perto", near_date.isoformat(), near)

    async with env.maker() as s:
        rows = (await s.execute(select(WorkoutPlanned).where(
            WorkoutPlanned.athlete_id == env.aid,
            WorkoutPlanned.deleted_at.is_(None),
        ))).scalars().all()
    per_day: dict = {}
    for w in rows:
        per_day.setdefault(w.planned_date, []).append(w)
    # Nunca dois treinos de planos diferentes no mesmo dia.
    assert all(len(v) == 1 for v in per_day.values())


async def test_expand_do_plano_distante_nao_rouba_dias_do_proximo(env):
    headers = await _auth(env.client)
    near_date = date.today() + timedelta(days=21)
    far_date = date.today() + timedelta(days=180)
    near = await _make_race(env, "Perto", near_date)
    far = await _make_race(env, "Longe", far_date)

    await _gen_and_expand(env, headers, "Plano Perto", near_date.isoformat(), near)
    before = None
    async with env.maker() as s:
        before = {(w.planned_date, w.name) for w in (await s.execute(
            select(WorkoutPlanned).where(WorkoutPlanned.athlete_id == env.aid,
                                         WorkoutPlanned.deleted_at.is_(None)))).scalars().all()}

    await _gen_and_expand(env, headers, "Plano Longe", far_date.isoformat(), far)
    async with env.maker() as s:
        rows = (await s.execute(select(WorkoutPlanned).where(
            WorkoutPlanned.athlete_id == env.aid,
            WorkoutPlanned.deleted_at.is_(None)))).scalars().all()
    after = {(w.planned_date, w.name) for w in rows}
    # Os dias do plano da prova próxima continuam intactos.
    assert before <= after


async def test_expand_responde_tss_dropped(env):
    headers = await _auth(env.client)
    when = date.today() + timedelta(days=60)
    rid = await _make_race(env, "Solo", when)
    result = await _gen_and_expand(env, headers, "Plano Solo", when.isoformat(), rid)
    assert "tss_dropped" in result
    assert result["tss_dropped"] >= 0.0
```

- [ ] **Step 2: Verify it fails** — estático: `expand_plan_to_daily` chama `allocate_days` esperando lista (quebra no unpack após a Task 2), não devolve `tss_dropped` e grava duplicatas em dias disputados.

- [ ] **Step 3: Write minimal implementation** — em `expand_plan_to_daily`:

(a) O clamp de descanso vira mínimo 1 (spec): trocar

```python
    rest = 1
    if profile is not None and profile.weekly_days:
        rest = max(0, min(3, 7 - int(profile.weekly_days)))
```
por
```python
    rest = 1
    if profile is not None and profile.weekly_days:
        rest = max(1, min(3, 7 - int(profile.weekly_days)))
```

(b) A chamada vira unpack:

```python
    days, tss_dropped = allocate_days(
        weeks, ftp=ftp, race_date=plan.race_date, rest_per_week=rest, today=today,
        blocked_days=frozenset(blocked),
    )
```

(c) Antes do loop de gravação, mapear dias ocupados por OUTROS planos ativos:

```python
    others = (await session.execute(
        select(TrainingPlan).where(
            TrainingPlan.athlete_id == athlete_id,
            TrainingPlan.id != plan_id,
            TrainingPlan.deleted_at.is_(None),
        )
    )).scalars().all()
    conflict: dict = {}
    if others:
        by_id = {p.id: p for p in others}
        rows = (await session.execute(
            select(WorkoutPlanned).where(
                WorkoutPlanned.athlete_id == athlete_id,
                WorkoutPlanned.source_plan_id.in_(list(by_id)),
                WorkoutPlanned.deleted_at.is_(None),
            )
        )).scalars().all()
        for r in rows:
            conflict[r.planned_date] = (r.id, by_id[r.source_plan_id].race_date)
```

(d) No loop de gravação, aplicar a regra (prova mais próxima vence):

```python
    written = 0
    for d in days:
        hit = conflict.get(d.planned_date)
        if hit is not None:
            other_id, other_race = hit
            if other_race is not None and other_race < plan.race_date:
                continue  # o outro plano atende prova mais próxima: dia é dele
            await session.execute(
                delete(WorkoutPlanned).where(WorkoutPlanned.id == other_id)
            )
        session.add(WorkoutPlanned(
            athlete_id=athlete_id, created_by=athlete_id,
            planned_date=d.planned_date, name=d.structure.get("name", "Treino"),
            workout_type=d.workout_type, planned_duration_s=d.planned_duration_s,
            planned_tss=d.planned_tss, structure=d.structure, description=d.description,
            source_plan_id=plan_id,
        ))
        written += 1
    await session.flush()
    return {
        "days": written,
        "tss_total": round(sum(d.planned_tss for d in days), 1),
        "tss_dropped": tss_dropped,
        "start": str(min((d.planned_date for d in days), default=today)),
        "end": str(max((d.planned_date for d in days), default=today)),
    }
```

(O delete idempotente das linhas do PRÓPRIO plano, já existente antes do loop,
permanece intocado.)

- [ ] **Step 4: Verify** — leitura confere; suíte completa na VM na Task 4.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/planning/plan_expander.py backend/app/tests/test_api/test_plan_expand_multiplano.py
git commit -m "feat(plans): prova mais próxima vence o dia + tss_dropped no expand"
```

---

### Task 4: Verificação completa + PR

- [ ] **Step 1: Suíte completa na VM** — comando das Global Constraints. Expected: tudo verde (os testes antigos de expand em `test_api/test_plan_expand.py` podem assumir a semana antiga — se falharem, atualizar as asserções de contagem/estrutura para o esqueleto novo, mantendo o espírito de cada teste).

- [ ] **Step 2: Web não muda** — `cd web && npx tsc --noEmit` por higiene. Expected: limpo.

- [ ] **Step 3: Push + PR**

```bash
git push -u origin feat/expansao-diaria-variada
gh pr create --title "feat(plans): expansão diária variada (longão, esqueleto semanal, multi-plano)" --body "..."
```

Corpo do PR: problema (semanas monótonas: mesmo Z2 todos os dias, saturação do teto 2,5×, sem longão; planos sobrepostos), decisões da spec, verificação (suíte VM), rollout (deploy `up -d --build api`; regenerar os 2 planos pelo botão).
