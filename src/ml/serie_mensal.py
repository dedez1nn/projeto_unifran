"""Previsão do total mensal de acidentes da cidade (próximos 12 meses).

Regressão de Poisson com sazonalidade por mês, ajustada de 2021 em diante.
Não usa tendência: no backtest (5 cortes de 12 meses, 2023-05 a 2025-05) a
tendência log-linear errava em média 22,7% porque extrapolava o salto de
2023, enquanto o nível médio desde 2021 com sazonalidade errou 15,1%, contra
22,8% do "mesmo mês do ano anterior" e 22,4% da média dos últimos 12 meses.
2019-2020 ficam de fora do ajuste pela queda atípica da pandemia.

Meses sem dados na fonte ficam fora do ajuste em vez de entrarem como zero.
O intervalo é de quase-Poisson: a variância observada costuma ser maior que
a média (sobredispersão), e o fator `phi` estimado nos resíduos alarga o
intervalo na medida certa.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor

HORIZONTE_MESES = 12
INICIO_AJUSTE = "2021-01"
CORTES_BACKTEST = ("2023-05", "2023-11", "2024-05", "2024-11", "2025-05")
_Z95 = 1.96


def serie_observada(df: pd.DataFrame) -> pd.DataFrame:
    meses = df["data_acidente"].dt.to_period("M")
    cont = meses.value_counts().sort_index()
    indice = pd.period_range(cont.index.min(), cont.index.max(), freq="M")
    cont = cont.reindex(indice, fill_value=0)
    observado = cont >= 0.3 * cont.median()
    return pd.DataFrame({"real": cont.where(observado).astype(float)}, index=indice)


def _features(indice: pd.PeriodIndex) -> np.ndarray:
    mes = np.array([p.month for p in indice])
    return np.stack([(mes == k).astype(float) for k in range(2, 13)], axis=1)


def _ajustar(serie: pd.DataFrame) -> PoissonRegressor:
    obs = serie[serie.index >= pd.Period(INICIO_AJUSTE, "M")].dropna(subset=["real"])
    return PoissonRegressor(alpha=1e-4, max_iter=2000).fit(_features(obs.index), obs["real"])


def _mape(real, previsto) -> float:
    real, previsto = np.asarray(real, float), np.asarray(previsto, float)
    ok = ~np.isnan(real) & ~np.isnan(previsto) & (real > 0)
    return float(np.mean(np.abs(previsto[ok] - real[ok]) / real[ok]) * 100)


def avaliar(serie: pd.DataFrame) -> dict:
    """MAPE médio dos 12 meses seguintes a cada corte, contra dois baselines."""
    erros = {"modelo": [], "mesmo_mes_ano_anterior": [], "media_12m": []}
    for corte in CORTES_BACKTEST:
        c = serie.index.get_loc(pd.Period(corte, "M"))
        treino, teste = serie.iloc[:c], serie.iloc[c:c + HORIZONTE_MESES]
        if len(teste) < HORIZONTE_MESES:
            continue
        erros["modelo"].append(_mape(teste["real"], _ajustar(treino).predict(_features(teste.index))))
        erros["mesmo_mes_ano_anterior"].append(_mape(teste["real"], serie["real"].shift(12).iloc[c:c + HORIZONTE_MESES]))
        erros["media_12m"].append(_mape(teste["real"], np.full(HORIZONTE_MESES, treino["real"].iloc[-12:].mean())))
    return {f"mape_{k}": float(np.mean(v)) for k, v in erros.items()} | {"cortes": list(CORTES_BACKTEST)}


def prever(serie: pd.DataFrame) -> pd.DataFrame:
    modelo = _ajustar(serie)
    obs = serie[serie.index >= pd.Period(INICIO_AJUSTE, "M")].dropna(subset=["real"])
    ajustado = modelo.predict(_features(obs.index))
    n_param = _features(obs.index[:1]).shape[1] + 1
    phi = max(float(np.sum((obs["real"] - ajustado) ** 2 / ajustado) / (len(obs) - n_param)), 1.0)

    futuro = pd.period_range(serie.index[-1] + 1, periods=HORIZONTE_MESES, freq="M")
    previsto = modelo.predict(_features(futuro))
    margem = _Z95 * np.sqrt(phi * previsto)

    historico = pd.DataFrame({"mes": serie.index.astype(str), "real": serie["real"].to_numpy(),
                              "previsto": modelo.predict(_features(serie.index)),
                              "limite_inferior": np.nan, "limite_superior": np.nan, "futuro": False})
    proximos = pd.DataFrame({"mes": futuro.astype(str), "real": np.nan, "previsto": previsto,
                             "limite_inferior": np.clip(previsto - margem, 0, None),
                             "limite_superior": previsto + margem, "futuro": True})
    return pd.concat([historico, proximos], ignore_index=True)
