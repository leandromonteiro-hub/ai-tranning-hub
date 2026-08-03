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
