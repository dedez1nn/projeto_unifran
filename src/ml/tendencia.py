"""Zonas em alta: células com mais acidentes nos últimos meses do que o
próprio histórico delas faria esperar.

O esperado de cada célula vem da fatia que ela tinha no total da cidade
antes da janela recente, aplicada ao total da cidade na janela. Comparar
fatias (e não contagens) neutraliza o que muda para a cidade inteira ao
mesmo tempo: meses sem dados na fonte (2025-11) e a queda de cobertura de
coordenadas em 2026 (64% contra 99% em 2025).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import poisson

JANELA_RECENTE_MESES = 6
MIN_ACIDENTES_RECENTES = 6
RAZAO_MINIMA = 1.5
P_MAXIMO = 0.01   # ~780 células testadas: limiar estrito para não acender célula por acaso


def zonas_em_alta(g: pd.DataFrame, ultimo_mes: int) -> pd.DataFrame:
    corte = ultimo_mes - JANELA_RECENTE_MESES
    recente = g[g["m"] > corte].groupby("celula")["w"].sum()
    antes = g[g["m"] <= corte].groupby("celula")["w"].sum()
    celulas = recente.index.union(antes.index)
    recente, antes = recente.reindex(celulas).fillna(0), antes.reindex(celulas).fillna(0)

    esperado = recente.sum() * antes / max(antes.sum(), 1e-9)
    n = np.round(recente).astype(int)
    p = pd.Series(np.where(esperado > 0, poisson.sf(n - 1, esperado.clip(lower=1e-9)), np.nan), index=celulas)
    razao = (recente / esperado).where(esperado > 0)
    em_alta = (n >= MIN_ACIDENTES_RECENTES) & (razao >= RAZAO_MINIMA) & (p < P_MAXIMO)
    return pd.DataFrame({"acidentes_recentes": recente, "esperado_recente": esperado,
                         "tendencia_razao": razao, "tendencia_p": p, "em_alta": em_alta.fillna(False)})
