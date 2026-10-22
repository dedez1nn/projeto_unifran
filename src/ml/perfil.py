"""Perfil de quando os acidentes acontecem (dia da semana x hora).

Para cada via do ranking, a fração dos acidentes dela em cada uma das 168
combinações dia x hora, suavizada em direção ao perfil da cidade (uma via
com poucos registros herda o formato da cidade em vez de ter horas "zeradas"
por acaso). Usa todos os anos (2019+), porque hora e logradouro existem desde
o início da série, mesmo sem coordenada.

Combinado com a previsão anual da via, dá o risco esperado de um dia/horário
específico (`GET /risco/simular` e `GET /risco/agora`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

ESCOPO_CIDADE = "__cidade__"
K_SUAVIZACAO = 50.0   # em acidentes: peso do perfil da cidade no perfil de cada via
_SLOTS = pd.MultiIndex.from_product([range(7), range(24)], names=["dia_semana", "hora"])


def _contagem(d: pd.DataFrame) -> pd.Series:
    return d.groupby(["dia_semana", "hora"]).size().reindex(_SLOTS, fill_value=0).astype(float)


def perfis(df: pd.DataFrame, vias: pd.Index) -> pd.DataFrame:
    d = df.dropna(subset=["hora"]).copy()
    d["hora"] = d["hora"].astype(int)
    cidade = _contagem(d)
    frac_cidade = cidade / cidade.sum()

    partes = [frac_cidade.rename("fracao").reset_index().assign(escopo=ESCOPO_CIDADE)]
    por_via = d[d["rua"].isin(vias)]
    for via, grupo in por_via.groupby("rua"):
        n = _contagem(grupo)
        frac = (n + K_SUAVIZACAO * frac_cidade) / (n.sum() + K_SUAVIZACAO)
        partes.append(frac.rename("fracao").reset_index().assign(escopo=via))
    return pd.concat(partes, ignore_index=True)[["escopo", "dia_semana", "hora", "fracao"]]


def quantis_taxa_hora(perfil: pd.DataFrame, vias: pd.DataFrame) -> list[float]:
    """Distribuição (101 quantis) de "acidentes esperados por ano numa hora
    específica da semana" entre todas as vias x 168 horas. A API usa para
    transformar o resultado de uma simulação em percentil (índice 0-100)."""
    p = perfil[perfil["escopo"] != ESCOPO_CIDADE]
    taxa = p["fracao"].to_numpy() * vias["acidentes_esperados"].reindex(p["escopo"]).to_numpy()
    return np.quantile(taxa[~np.isnan(taxa)], np.linspace(0, 1, 101)).tolist()
