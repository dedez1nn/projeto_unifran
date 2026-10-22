"""Cálculo da simulação de risco a partir do que o treino publicou.

Funções puras (sem banco), para a rota só buscar as linhas e repassar. A
ideia é decompor o risco em dois fatores que a base sustenta:

- quantos acidentes a via deve ter nos próximos 12 meses (`RiscoVia`);
- que fração deles cai num dia da semana e horário (`RiscoPerfilHorario`).

O produto dá acidentes esperados por ano naquela janela. O índice 0-100 põe
esse valor (por hora) numa escala logarítmica entre a mediana (0) e o
percentil 99 (100) de todas as vias x 168 horas da semana. Percentil puro
não servia: as vias grandes ficavam sempre em 94-99 e o horário quase não
mudava o resultado. Com os cortes 70 (ALTO) e 40 (MÉDIO), ~7% das
combinações via x hora ficam ALTO e ~13% MÉDIO, perto dos 5%/15% das zonas.
Clima não entra: a base registra o clima de cada acidente, mas não por
quanto tempo choveu, então não existe denominador para medir o efeito.
"""

from __future__ import annotations

import math

AVISO_CLIMA = (
    "O clima não entra no cálculo: a base registra o clima de cada acidente, "
    "mas não por quanto tempo choveu, então não dá para medir o efeito da chuva."
)


CORTE_ALTO, CORTE_MEDIO = 70, 40


def indice_risco(taxa_hora: float, quantis: list[float]) -> int:
    """`quantis` tem 101 pontos (0%, 1%, ..., 100%) publicados pelo treino."""
    piso, teto = quantis[50], quantis[99]
    if taxa_hora <= piso or teto <= piso:
        return 0
    return round(100 * min(math.log(taxa_hora / piso) / math.log(teto / piso), 1.0))


def nivel_por_indice(indice: int) -> str:
    if indice >= CORTE_ALTO:
        return "ALTO"
    if indice >= CORTE_MEDIO:
        return "MEDIO"
    return "BAIXO"


def _decimal(x: float) -> str:
    return f"{x:.1f}".replace(".", ",")


def _hora(h: int) -> str:
    return f"{h:02d}h"


def simular(
    *,
    via: str,
    acidentes_ano: float,
    fracoes: dict[tuple[int, int], float],
    dia_semana: int,
    horas: list[int],
    quantis: list[float],
    nivel_via: str,
) -> dict:
    horas = sorted(set(horas))
    fracao_janela = sum(fracoes.get((dia_semana, h), 0.0) for h in horas)
    esperado_janela = acidentes_ano * fracao_janela
    por_hora = esperado_janela / len(horas)
    # 1,0 = a janela tem exatamente a média por hora da própria via
    intensidade = (fracao_janela / len(horas)) * 168
    indice = indice_risco(por_hora, quantis)
    nivel = nivel_por_indice(indice)

    no_dia = sorted(range(24), key=lambda h: fracoes.get((dia_semana, h), 0.0), reverse=True)
    pico = sorted(no_dia[:3])

    fatores = [
        f"A via tem {acidentes_ano:.0f} acidentes previstos para os próximos 12 meses "
        f"(nível {nivel_via} entre as vias da cidade).",
        f"Nesse dia e horário ela concentra {_decimal(intensidade)}x a média por hora dela.",
        f"Horas de maior concentração nesse dia: {', '.join(_hora(h) for h in pico)}.",
        AVISO_CLIMA,
    ]
    return {
        "via": via, "dia_semana": dia_semana, "horas": horas,
        "acidentes_esperados_ano": acidentes_ano,
        "acidentes_esperados_janela": esperado_janela,
        "intensidade": intensidade, "indice": indice, "nivel_risco": nivel,
        "horas_pico_no_dia": pico, "fatores": fatores,
    }


def quadrado(lat: float, lon: float, tamanho: float) -> list[list[list[float]]]:
    """Polígono GeoJSON ([lon, lat], anel fechado) da célula centrada em lat/lon."""
    m = tamanho / 2
    anel = [[lon - m, lat - m], [lon + m, lat - m], [lon + m, lat + m], [lon - m, lat + m], [lon - m, lat - m]]
    return [[[round(x, 6), round(y, 6)] for x, y in anel]]
