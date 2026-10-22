"""Previsão de acidentes por célula (~550 m) para os próximos 12 meses.

Adaptado do `modelo_risco_acidentes_v3.py` do time de ML, com três correções
apontadas na revisão:

1. A alocação fracionada por logradouro (acidente sem coordenada distribuído
   entre as células onde a mesma rua tem acidentes geocodificados) usava o
   período inteiro, inclusive o futuro de cada corte do backtest. Agora os
   pesos de cada corte usam só os acidentes até aquele corte (`alocar`).
2. `escolher_modelo` podia eleger `BASE_taxa`, mas o ranking só sabia aplicar
   `GBM`/`MISTO_GBM_EB` e caía em `BASE_EB` sem avisar. Agora o backtest e o
   ranking usam a mesma função (`prever`), então vale o que foi escolhido.
3. O ranking exporta a rua principal de cada célula (o site precisa de um
   nome, não de uma coordenada) e o agregado por via.

Também passou a contar a madrugada como "noite" (antes era só `hora >= 18`).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import (
    average_precision_score,
    mean_absolute_error,
    mean_poisson_deviance,
    roc_auc_score,
)

TAMANHO_CELULA = 0.005          # graus (~550 m)
HORIZONTE_MESES = 12
INICIO_COORDENADAS = "2023-01"  # antes disso a cobertura de coordenadas é 0-35%
MIN_HISTORICO_MESES = 6
BBOX = dict(lat=(-22.0, -20.0), lon=(-48.0, -47.0))
SEMENTE = 42
FRACAO_ALTO, FRACAO_MEDIO = 0.05, 0.15
PLACEHOLDER_MIN_N, PLACEHOLDER_MIN_ENDERECOS = 20, 10   # ponto repetido com muitos endereços distintos
MIN_ACID_RUA = 3                # mínimo de acidentes geocodificados na rua para recuperar por logradouro
PODA_PESO = 0.02                # descarta células com <2% do peso da rua (e renormaliza)
K_EB = 12.0                     # força (em meses) do prior da vizinhança na taxa suavizada
ORIGENS_BACKTEST = (21, 23, 25, 27)   # cortes do backtest (alvo de 12 meses completo)
MIN_ACID_VIA = 15               # vias com menos acidentes-equivalentes que isso não entram no ranking de vias

PARAMS_GBM = dict(loss="poisson", max_depth=3, learning_rate=0.05, max_iter=250,
                  min_samples_leaf=40, l2_regularization=1.0, random_state=SEMENTE)

MODELOS = ("BASE_taxa", "BASE_12m", "BASE_EB", "GBM", "MISTO_GBM_EB")
COLS_X = ["r_total", "r_12", "r_6", "r_3", "frac_meses_ativos", "viz1_rate", "viz2_rate", "eb_rate",
          "frac_noite", "frac_fds", "frac_rodovia", "hist_cap", "lat", "lon"]
_COLS_G = ["num_acidente", "celula", "gi", "gj", "m", "w", "obito", "noite", "fim_de_semana",
           "rodovia", "imputada", "rua"]


@dataclass
class BaseGeo:
    """Acidentes de 2023+ separados em geocodificados (`validos`) e
    recuperáveis por logradouro (`sem_coord`), mais o calendário de meses
    observados (`cum`: soma acumulada de meses com dados na fonte)."""

    validos: pd.DataFrame
    sem_coord: pd.DataFrame
    p0: pd.Period
    cum: np.ndarray
    resumo: dict = field(default_factory=dict)

    @property
    def ultimo_mes(self) -> int:
        return len(self.cum) - 1

    def mes(self, m: int) -> str:
        return str(self.p0 + m)


# ----------------------------------------------------------------------------
# 1. Base geográfica
# ----------------------------------------------------------------------------
def preparar_geo(df: pd.DataFrame) -> BaseGeo:
    d = df[df["data_acidente"] >= INICIO_COORDENADAS + "-01"].copy()
    p0 = pd.Period(INICIO_COORDENADAS, "M")
    d["m"] = d["data_acidente"].dt.to_period("M").map(lambda p: (p - p0).n)
    d["rodovia"] = d["rua"].str.match(r"^(SP|BR|RODOVIA|VIA |ANHANGUERA|VICINAL|ESTRADA)").astype(float)
    d["noite"] = ((d["hora"] >= 18) | (d["hora"] < 6)).astype(float)

    ok = d["latitude"].between(*BBOX["lat"]) & d["longitude"].between(*BBOX["lon"])
    # Placeholders: mesma coordenada exata usada para muitos endereços
    # diferentes (típico de rodovia). São uma propriedade do geocodificador,
    # não do desfecho, por isso podem ser detectados com o período inteiro.
    chave = d["latitude"].round(6).astype(str) + "_" + d["longitude"].round(6).astype(str)
    grp = d[ok].groupby(chave[ok]).agg(n=("num_acidente", "size"), nend=("rua", "nunique"))
    placeholders = set(grp[(grp["n"] >= PLACEHOLDER_MIN_N) & (grp["nend"] >= PLACEHOLDER_MIN_ENDERECOS)].index)
    eh_ph = ok & chave.isin(placeholders)
    valido = ok & ~eh_ph

    v = d[valido].copy()
    v["gi"] = np.round(v["latitude"] / TAMANHO_CELULA).astype(int)
    v["gj"] = np.round(v["longitude"] / TAMANHO_CELULA).astype(int)
    v["celula"] = v["gi"].astype(str) + "_" + v["gj"].astype(str)
    v["w"] = 1.0
    v["imputada"] = 0

    sem = d[~valido & (d["rua"] != "")].copy()
    sem_rua = int((~valido & (d["rua"] == "")).sum())

    # Mês quase vazio na fonte = não observado (ex.: 2025-11), não "zero acidentes".
    cont = d["m"].value_counts()
    ref = cont.median()
    ultimo = int(d["m"].max())
    obs = np.array([1 if cont.get(k, 0) >= 0.3 * ref else 0 for k in range(ultimo + 1)])
    ausentes = [str(p0 + k) for k in range(ultimo + 1) if obs[k] == 0]

    resumo = dict(
        acidentes_desde_2023=int(len(d)), coord_valida=int(valido.sum()),
        sem_coord_ou_zero=int((~ok).sum()), em_placeholder=int(eh_ph.sum()),
        pontos_placeholder=len(placeholders), sem_coord_sem_rua=sem_rua,
        meses=ultimo + 1, meses_ausentes=ausentes,
    )
    return BaseGeo(validos=v, sem_coord=sem, p0=p0, cum=np.cumsum(obs), resumo=resumo)


def alocar(base: BaseGeo, ate_m: int) -> pd.DataFrame:
    """Uma linha por acidente x célula (peso `w`). Os acidentes sem
    coordenada são distribuídos entre as células da mesma rua com pesos
    calculados só com os geocodificados até `ate_m`: o backtest nunca usa a
    distribuição espacial do futuro para montar o passado."""
    v = base.validos
    ref = v[(v["m"] <= ate_m) & (v["rua"] != "")]
    n = ref.groupby(["rua", "celula"]).size().rename("n").reset_index()
    tot = n.groupby("rua")["n"].transform("sum")
    n = n[tot >= MIN_ACID_RUA].copy()
    n["p"] = n["n"] / n.groupby("rua")["n"].transform("sum")
    n = n[n["p"] >= PODA_PESO].copy()
    n["p"] = n["p"] / n.groupby("rua")["p"].transform("sum")
    ij = v.drop_duplicates("celula").set_index("celula")[["gi", "gj"]]
    n = n.join(ij, on="celula")

    imp = base.sem_coord.merge(n[["rua", "celula", "p", "gi", "gj"]], on="rua", how="inner")
    imp["w"] = imp["p"]
    imp["imputada"] = 1
    g = pd.concat([v[_COLS_G], imp[_COLS_G]], ignore_index=True)
    g["gi"], g["gj"] = g["gi"].astype(int), g["gj"].astype(int)
    return g


def n_obs(cum: np.ndarray, lo: int, hi: int) -> int:
    """Meses observados em (lo, hi]."""
    c = lambda k: 0 if k < 0 else int(cum[min(k, len(cum) - 1)])
    return c(hi) - c(lo)


# ----------------------------------------------------------------------------
# 2. Features por célula (só passado, estacionárias) e alvo (futuro)
# ----------------------------------------------------------------------------
VIZ1 = [(a, b) for a in (-1, 0, 1) for b in (-1, 0, 1) if (a, b) != (0, 0)]
VIZ2 = [(a, b) for a in range(-2, 3) for b in range(-2, 3) if (a, b) != (0, 0)]


def features_celulas(g: pd.DataFrame, origem: int, cum: np.ndarray) -> pd.DataFrame:
    h = g[g["m"] <= origem].copy()
    obs_tot = max(n_obs(cum, -1, origem), 1)
    h["wo"], h["wn"] = h["w"] * h["obito"], h["w"] * h["noite"]
    h["wf"], h["wr"] = h["w"] * h["fim_de_semana"], h["w"] * h["rodovia"]
    a = h.groupby("celula").agg(gi=("gi", "first"), gj=("gj", "first"), n_total=("w", "sum"),
                                n_obitos=("wo", "sum"), meses_ativos=("m", "nunique"),
                                s_noite=("wn", "sum"), s_fds=("wf", "sum"), s_rod=("wr", "sum"))
    a["r_total"] = a["n_total"] / obs_tot
    for k in (12, 6, 3):
        lo = max(origem - k, -1)
        o = max(n_obs(cum, lo, origem), 1)
        a[f"r_{k}"] = h[h["m"] > lo].groupby("celula")["w"].sum().reindex(a.index).fillna(0) / o
    a["frac_meses_ativos"] = a["meses_ativos"] / obs_tot
    nt = dict(zip(zip(a["gi"], a["gj"]), a["n_total"]))
    v1 = np.array([sum(nt.get((i + x, j + y), 0.0) for x, y in VIZ1) for i, j in zip(a["gi"], a["gj"])])
    v2 = np.array([sum(nt.get((i + x, j + y), 0.0) for x, y in VIZ2) for i, j in zip(a["gi"], a["gj"])])
    a["viz1_rate"] = v1 / 8 / obs_tot                    # taxa média mensal das 8 vizinhas
    a["viz2_rate"] = v2 / 24 / obs_tot                   # idem, anel 5x5
    a["eb_rate"] = (a["n_total"] + K_EB * a["viz1_rate"]) / (obs_tot + K_EB)   # Gamma-Poisson
    tw = a["n_total"].replace(0, np.nan)
    a["frac_noite"], a["frac_fds"] = a["s_noite"] / tw, a["s_fds"] / tw
    a["frac_rodovia"] = a["s_rod"] / tw
    a["hist_cap"] = min(obs_tot, 12)                     # limitado: evita extrapolar além do visto no treino
    a["lat"], a["lon"] = a["gi"] * TAMANHO_CELULA, a["gj"] * TAMANHO_CELULA
    return a


def alvo_futuro(g, origem, celulas, horizonte, cum):
    """Acidentes (e óbitos) nos próximos `horizonte` meses, reescalados quando
    algum mês da janela não tem dados na fonte."""
    f = g[(g["m"] > origem) & (g["m"] <= origem + horizonte)]
    o = n_obs(cum, origem, origem + horizonte)
    esc = horizonte / o if o > 0 else np.nan
    y = f.groupby("celula")["w"].sum().reindex(celulas).fillna(0) * esc
    yo = (f["w"] * f["obito"]).groupby(f["celula"]).sum().reindex(celulas).fillna(0) * esc
    return y, yo


def montar_painel(base: BaseGeo, origens, horizonte: int) -> pd.DataFrame:
    partes = []
    for o in origens:
        g = alocar(base, o)
        X = features_celulas(g, o, base.cum)
        y, yo = alvo_futuro(g, o, X.index, horizonte, base.cum)
        partes.append(X.assign(y=y.values, y_obito=yo.values, origem=o))
    return pd.concat(partes).dropna(subset=["y"])


def prever(nome: str, X: pd.DataFrame, gbm: np.ndarray, horizonte: int) -> np.ndarray:
    """Previsão de acidentes em `horizonte` meses por cada modelo candidato.
    Usada tanto no backtest quanto no ranking final."""
    eb = X["eb_rate"].to_numpy() * horizonte
    return {
        "BASE_taxa": X["r_total"].to_numpy() * horizonte,
        "BASE_12m": X["r_12"].to_numpy() * horizonte,
        "BASE_EB": eb,
        "GBM": gbm,
        "MISTO_GBM_EB": 0.5 * gbm + 0.5 * eb,
    }[nome]


# ----------------------------------------------------------------------------
# 3. Métricas e backtest
# ----------------------------------------------------------------------------
def captura_topk(score, real: pd.Series, k: int) -> float:
    top = pd.Series(np.asarray(score), index=real.index).sort_values(ascending=False).head(k).index
    return float(real[top].sum() / max(real.sum(), 1e-9))


def metricas(pred, y: pd.Series) -> dict:
    s = pd.Series(np.asarray(pred, dtype=float), index=y.index)
    p = np.clip(s.to_numpy(), 1e-3, None)
    n5 = max(int(len(y) * 0.05), 1)
    return {
        "spearman": float(spearmanr(s, y)[0]),
        "captura_top5pct": captura_topk(s, y, n5),
        "captura_top50": captura_topk(s, y, 50),
        "captura_top100": captura_topk(s, y, 100),
        "mae": float(mean_absolute_error(y, p)),
        "dev_poisson": float(mean_poisson_deviance(y, p)),
        "previsto_sobre_real": float(p.sum() / y.sum()),
    }


def _treinar_gbm(painel: pd.DataFrame) -> HistGradientBoostingRegressor:
    return HistGradientBoostingRegressor(**PARAMS_GBM).fit(painel[COLS_X], painel["y"])


def backtest_rolling(base: BaseGeo, horizonte: int = HORIZONTE_MESES):
    """Para cada corte, treina só com alvos que terminam até o corte e mede a
    previsão dos 12 meses seguintes. Os cortes se sobrepõem (janelas de 12
    meses espaçadas de 2), então a média é mais estável do que seria com
    janelas independentes."""
    linhas, testes = [], {}
    for o in ORIGENS_BACKTEST:
        if o + horizonte > base.ultimo_mes:
            continue
        treino = montar_painel(base, range(MIN_HISTORICO_MESES - 1, o - horizonte + 1), horizonte)
        teste = montar_painel(base, [o], horizonte)
        gbm = _treinar_gbm(treino).predict(teste[COLS_X])
        for nome in MODELOS:
            teste[nome] = prever(nome, teste, gbm, horizonte)
            linhas.append({"modelo": nome, "origem": base.mes(o), **metricas(teste[nome], teste["y"])})
        testes[o] = teste
    por_origem = pd.DataFrame(linhas)
    media = por_origem.groupby("modelo").mean(numeric_only=True).loc[list(MODELOS)]
    return media, por_origem, testes


def escolher_modelo(media: pd.DataFrame) -> str:
    """Menor desvio de Poisson médio no backtest. `BASE_12m` fica de fora:
    com só 12 meses de histórico ela é instável demais (desvio quase 2x)."""
    return str(media["dev_poisson"].drop("BASE_12m").idxmin())


def avaliar_indice_obitos(testes: dict) -> pd.DataFrame:
    """Que fração dos óbitos FUTUROS cai nas top-k células, ordenando por
    acidentes esperados ou por histórico. Óbito por célula é raro demais
    para ser previsto diretamente; isto mostra qual ordenação ajuda mais."""
    linhas = []
    for o, te in testes.items():
        y = te["y_obito"]
        if y.sum() <= 0:
            continue
        candidatos = {"acidentes_esperados_gbm": te["GBM"], "historico_acidentes": te["r_total"],
                      "historico_obitos": te["n_obitos"]}
        for nome, s in candidatos.items():
            linhas.append({"ordenacao": nome, "obitos_no_teste": float(y.sum()),
                           "captura_obitos_top50": captura_topk(s, y, 50),
                           "captura_obitos_top100": captura_topk(s, y, 100)})
    colunas = ["ordenacao", "obitos_no_teste", "captura_obitos_top50", "captura_obitos_top100"]
    return pd.DataFrame(linhas, columns=colunas).groupby("ordenacao").mean(numeric_only=True)


def avaliar_gravidade_por_horario(df: pd.DataFrame, corte: str = "2025-01-01") -> dict:
    """P(óbito | acidente) só com hora/dia/mês. Fica como diagnóstico: o que
    mais explica gravidade (tipo de colisão, veículos) só é conhecido depois
    do acidente, então isto não é publicado como índice no site."""
    d = df.dropna(subset=["hora"]).copy()
    d["mes"] = d["data_acidente"].dt.month
    feats = ["hora", "dia_semana", "mes", "fim_de_semana"]
    tr, te = d[d["data_acidente"] < corte], d[d["data_acidente"] >= corte]
    clf = HistGradientBoostingClassifier(max_depth=3, learning_rate=0.05, max_iter=150,
                                         min_samples_leaf=100, l2_regularization=1.0,
                                         random_state=SEMENTE).fit(tr[feats], tr["obito"])
    p = clf.predict_proba(te[feats])[:, 1]
    return {"taxa_base_obito_teste": float(te["obito"].mean()), "auc": float(roc_auc_score(te["obito"], p)),
            "pr_auc": float(average_precision_score(te["obito"], p)), "pr_auc_do_acaso": float(te["obito"].mean())}


# ----------------------------------------------------------------------------
# 4. Modelo final, ranking de células e de vias
# ----------------------------------------------------------------------------
def _niveis(valores: pd.Series) -> pd.Series:
    ordem = valores.rank(ascending=False, method="first")
    n = len(valores)
    nivel = pd.Series("BAIXO", index=valores.index)
    nivel[ordem <= int(n * (FRACAO_ALTO + FRACAO_MEDIO))] = "MEDIO"
    nivel[ordem <= max(int(n * FRACAO_ALTO), 1)] = "ALTO"
    return nivel


def gerar_ranking(base: BaseGeo, modelo: str, horizonte: int = HORIZONTE_MESES):
    """Treina o GBM com todos os cortes disponíveis e prevê os próximos
    `horizonte` meses a partir do último mês da base. Retorna (células, vias, g)."""
    ultimo = base.ultimo_mes
    painel = montar_painel(base, range(MIN_HISTORICO_MESES - 1, ultimo - horizonte + 1), horizonte)
    g = alocar(base, ultimo)
    X = features_celulas(g, ultimo, base.cum)
    gbm = _treinar_gbm(painel).predict(X[COLS_X]) if modelo in ("GBM", "MISTO_GBM_EB") else np.zeros(len(X))
    X["acidentes_esperados"] = prever(modelo, X, gbm, horizonte)
    X["n_12"] = X["r_12"] * 12

    por_rua = g[g["rua"] != ""].groupby(["celula", "rua"])["w"].sum()
    X["rua_principal"] = por_rua.groupby(level="celula").idxmax().map(lambda t: t[1]).reindex(X.index)
    X["nivel_risco"] = _niveis(X["acidentes_esperados"])
    ini, fim = base.mes(ultimo + 1), base.mes(ultimo + horizonte)
    X["janela_previsao"] = f"{ini} a {fim}"
    celulas = X.sort_values("acidentes_esperados", ascending=False)

    # Vias: cada célula reparte sua previsão entre as ruas na proporção do
    # histórico dela, e a via soma as fatias de todas as células onde aparece.
    fatia = por_rua / por_rua.groupby(level="celula").transform("sum")
    esperado = fatia * celulas["acidentes_esperados"].reindex(fatia.index.get_level_values("celula")).to_numpy()
    lat = celulas["lat"].reindex(fatia.index.get_level_values("celula")).to_numpy()
    lon = celulas["lon"].reindex(fatia.index.get_level_values("celula")).to_numpy()
    tmp = pd.DataFrame({"rua": fatia.index.get_level_values("rua"), "esperado": esperado.to_numpy(),
                        "n": por_rua.to_numpy(), "lat_w": lat * por_rua.to_numpy(),
                        "lon_w": lon * por_rua.to_numpy()})
    vias = tmp.groupby("rua").agg(acidentes_esperados=("esperado", "sum"), n_total=("n", "sum"),
                                  lat_w=("lat_w", "sum"), lon_w=("lon_w", "sum"))
    vias = vias[vias["n_total"] >= MIN_ACID_VIA].copy()
    vias["lat"], vias["lon"] = vias["lat_w"] / vias["n_total"], vias["lon_w"] / vias["n_total"]
    vias["nivel_risco"] = _niveis(vias["acidentes_esperados"])
    vias = vias.drop(columns=["lat_w", "lon_w"]).sort_values("acidentes_esperados", ascending=False)
    return celulas, vias, g
