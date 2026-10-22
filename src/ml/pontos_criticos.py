"""Pontos críticos: aglomerados de acidentes com óbito (DBSCAN).

Usa só óbito porque é o único desfecho de gravidade registrado de forma
consistente em todos os anos (ferido não fatal praticamente some a partir de
2023). Não há rótulo de treino nem previsão aqui, só a localização do que já
aconteceu, então não existe risco de vazamento. As coordenadas-placeholder
(ver `ocorrencia.preparar_geo`) já vêm excluídas, senão formariam
"aglomerados" falsos num único ponto de rodovia.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN

RAIO_METROS = 150
MIN_ACIDENTES_FATAIS = 3
RAIO_MINIMO_EXIBIDO = 50
_RAIO_TERRA = 6_371_000.0


def _distancia_m(lat, lon, lat0, lon0):
    la, lo, la0, lo0 = map(np.radians, (lat, lon, lat0, lon0))
    a = np.sin((la - la0) / 2) ** 2 + np.cos(la) * np.cos(la0) * np.sin((lo - lo0) / 2) ** 2
    return 2 * _RAIO_TERRA * np.arcsin(np.sqrt(a))


def pontos_criticos(validos: pd.DataFrame) -> pd.DataFrame:
    fatais = validos[validos["obito"] == 1].reset_index(drop=True)
    if len(fatais) < MIN_ACIDENTES_FATAIS:
        return pd.DataFrame()
    coords = np.radians(fatais[["latitude", "longitude"]].to_numpy())
    rotulos = DBSCAN(eps=RAIO_METROS / _RAIO_TERRA, min_samples=MIN_ACIDENTES_FATAIS,
                     metric="haversine", algorithm="ball_tree").fit_predict(coords)
    fatais["grupo"] = rotulos

    linhas = []
    for _, c in fatais[fatais["grupo"] >= 0].groupby("grupo"):
        lat, lon = c["latitude"].mean(), c["longitude"].mean()
        ruas = c.loc[c["rua"] != "", "rua"]
        linhas.append({
            "lat": lat, "lon": lon,
            "raio_m": max(float(_distancia_m(c["latitude"], c["longitude"], lat, lon).max()), RAIO_MINIMO_EXIBIDO),
            "n_acidentes_fatais": int(len(c)),
            "n_obitos": int(c["qtde_obitos"].sum()),
            "rua_principal": ruas.mode().iloc[0] if not ruas.empty else None,
            "primeiro": c["data_acidente"].min().date(),
            "ultimo": c["data_acidente"].max().date(),
        })
    return (pd.DataFrame(linhas)
            .sort_values(["n_obitos", "n_acidentes_fatais"], ascending=False)
            .reset_index(drop=True))
