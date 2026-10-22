from app.services import risco_service

# 101 quantis: mediana = 0.1, p99 = 1.0
QUANTIS = [0.0] * 50 + [0.1] * 49 + [1.0, 5.0]


def test_indice_risco_vai_de_0_na_mediana_a_100_no_p99():
    assert risco_service.indice_risco(0.05, QUANTIS) == 0
    assert risco_service.indice_risco(0.1, QUANTIS) == 0
    assert risco_service.indice_risco(1.0, QUANTIS) == 100
    assert risco_service.indice_risco(50.0, QUANTIS) == 100
    # escala logarítmica: a média geométrica entre piso e teto fica no meio
    assert risco_service.indice_risco(0.1 * 10 ** 0.5, QUANTIS) == 50


def test_nivel_por_indice_usa_os_mesmos_cortes_do_front():
    assert risco_service.nivel_por_indice(70) == "ALTO"
    assert risco_service.nivel_por_indice(69) == "MEDIO"
    assert risco_service.nivel_por_indice(40) == "MEDIO"
    assert risco_service.nivel_por_indice(39) == "BAIXO"


def test_simular_com_perfil_uniforme_tem_intensidade_1():
    uniforme = {(d, h): 1 / 168 for d in range(7) for h in range(24)}
    r = risco_service.simular(via="RUA X", acidentes_ano=168.0, fracoes=uniforme, dia_semana=2,
                              horas=[8, 9, 9], quantis=QUANTIS, nivel_via="MEDIO")
    assert r["horas"] == [8, 9]
    assert abs(r["acidentes_esperados_janela"] - 2.0) < 1e-9
    assert abs(r["intensidade"] - 1.0) < 1e-9
    assert r["fatores"][-1] == risco_service.AVISO_CLIMA


def test_simular_destaca_as_horas_de_pico_do_dia():
    fracoes = {(0, h): 0.001 for h in range(24)}
    fracoes.update({(0, 7): 0.3, (0, 18): 0.4, (0, 12): 0.2})
    r = risco_service.simular(via="RUA X", acidentes_ano=10.0, fracoes=fracoes, dia_semana=0,
                              horas=[18], quantis=QUANTIS, nivel_via="ALTO")
    assert r["horas_pico_no_dia"] == [7, 12, 18]


def test_quadrado_e_um_anel_fechado_lon_lat():
    anel = risco_service.quadrado(-21.0, -47.0, 0.01)[0]
    assert anel[0] == anel[-1]
    assert anel[0] == [-47.005, -21.005]
    assert len(anel) == 5
