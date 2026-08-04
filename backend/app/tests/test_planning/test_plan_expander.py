"""allocate_days v2: esqueleto semanal + distribuição de TSS (spec 2026-08-03, rev. 2026-08-04)."""
from datetime import date

from app.models.enums import BlockType, WorkoutType
from app.services.planning.plan_expander import WeekSpec, allocate_days

FTP = 250.0
MON = date(2026, 1, 5)  # segunda-feira
RACE_FAR = date(2026, 12, 31)


def _base_week(tss=650.0):
    return WeekSpec(MON, BlockType.BASE, tss, False)


def test_longao_no_sabado_com_40pct():
    days, _ = allocate_days([_base_week()], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    saturday = [d for d in days if d.planned_date.weekday() == 5]
    assert len(saturday) == 1
    assert "Longão" in saturday[0].structure["name"]
    assert saturday[0].planned_tss >= 0.30 * 650  # ~40% com tolerância de clamp
    assert 2 * 3600 <= saturday[0].planned_duration_s <= 5 * 3600


def test_domingo_sempre_off():
    weeks = [WeekSpec(MON, BlockType.BASE, 650.0, False),
             WeekSpec(date(2026, 1, 12), BlockType.BUILD, 700.0, False),
             WeekSpec(date(2026, 1, 19), BlockType.RECOVERY, 400.0, True),
             WeekSpec(date(2026, 1, 26), BlockType.TAPER, 250.0, False)]
    days, _ = allocate_days(weeks, ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    assert all(d.planned_date.weekday() != 6 for d in days)


def test_dia_flex_absorve_ate_3h30():
    days, _ = allocate_days([_base_week(tss=900.0)], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    by_wd = {d.planned_date.weekday(): d for d in days}
    # Quarta absorve o excedente e cresce além dos 90min antigos…
    assert by_wd[2].planned_duration_s > 90 * 60
    # …mas nunca passa de 3h30; demais dias de semana idem.
    for wd, d in by_wd.items():
        if wd != 5:  # tudo menos o longão
            assert d.planned_duration_s <= 210 * 60


def test_descansos_seg_sex_qua_com_rest_3():
    days, _ = allocate_days([_base_week()], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=3, today=MON)
    weekdays = {d.planned_date.weekday() for d in days}
    assert 0 not in weekdays and 4 not in weekdays and 2 not in weekdays
    assert 5 in weekdays  # longão sobrevive


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
    assert "tempo" in by_wd[5].structure["name"].lower()


def test_deload_sem_longao_mas_entrega_o_alvo():
    wk = WeekSpec(MON, BlockType.RECOVERY, 400.0, True)
    days, _ = allocate_days([wk], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    for d in days:
        assert d.planned_duration_s <= 180 * 60  # deload: no máx 3h/dia
        assert "Longão" not in d.structure["name"]
    # Rev. 2026-08-04: o deload escala os dias de Z2 para perto do alvo.
    assert sum(d.planned_tss for d in days) >= 250


def test_qualidade_estendida_com_z2_quando_sobra_tss():
    days, _ = allocate_days([_base_week(tss=900.0)], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    by_wd = {d.planned_date.weekday(): d for d in days}
    # Ter (sweet spot) ganha extensão Z2: bem mais que os 71min do template…
    assert by_wd[1].planned_duration_s > 150 * 60
    assert by_wd[1].planned_duration_s <= 210 * 60
    # …sem perder a identidade do treino.
    assert by_wd[1].workout_type == WorkoutType.SWEET_SPOT
    assert "Sweet Spot" in by_wd[1].structure["name"]


def test_sexta_vira_z2_leve_quando_sobra_tss():
    days, _ = allocate_days([_base_week(tss=900.0)], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    by_wd = {d.planned_date.weekday(): d for d in days}
    assert by_wd[4].workout_type == WorkoutType.ENDURANCE
    assert 45 * 60 < by_wd[4].planned_duration_s <= 120 * 60


def test_sexta_continua_regenerativa_sem_sobra():
    # Semana leve: tudo cabe sem tocar na sexta.
    days, _ = allocate_days([_base_week(tss=350.0)], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON)
    by_wd = {d.planned_date.weekday(): d for d in days}
    assert by_wd[4].workout_type == WorkoutType.RECOVERY
    assert by_wd[4].planned_duration_s == 45 * 60


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


def test_prova_no_domingo_tem_openers_na_sexta():
    race = date(2026, 1, 11)  # domingo
    wk = WeekSpec(MON, BlockType.TAPER, 250.0, False)
    days, _ = allocate_days([wk], ftp=FTP, race_date=race,
                            rest_per_week=1, today=MON)
    by_date = {d.planned_date: d for d in days}
    assert date(2026, 1, 9) in by_date  # sex = prova - 2
    assert "Openers" in by_date[date(2026, 1, 9)].structure["name"]
    # Domingo (dia da prova) segue sem treino prescrito.
    assert race not in by_date


def test_dias_bloqueados_continuam_pulados():
    blocked = frozenset({date(2026, 1, 7), date(2026, 1, 8)})
    days, _ = allocate_days([_base_week()], ftp=FTP, race_date=RACE_FAR,
                            rest_per_week=1, today=MON, blocked_days=blocked)
    assert {d.planned_date for d in days}.isdisjoint(blocked)


def test_janela_respeita_today_e_race():
    days, _ = allocate_days([_base_week()], ftp=FTP, race_date=date(2026, 1, 9),
                            rest_per_week=1, today=date(2026, 1, 7))
    assert all(date(2026, 1, 7) <= d.planned_date <= date(2026, 1, 9) for d in days)
