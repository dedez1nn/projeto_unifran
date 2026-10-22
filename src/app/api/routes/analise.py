"""Exploração dos dados oficiais dentro do próprio site (sem mandar para o
portal do InfoSiga): resumo, série, distribuições, ranking de vias, perfil
das vítimas, qualidade dos dados, exportação e comparação entre cidades.

Todas as rotas de sinistros aceitam os mesmos filtros (`Filtros`), que são
os de `GET /sinistros` mais `via` e `turno`. A ficha de uma via usa `via`;
a de uma zona, a bounding box da célula (`lat_min` ... `lon_max`).
"""

import csv
import datetime as dt
import io
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import case, func
from sqlalchemy.orm import Query as SAQuery
from sqlalchemy.orm import Session

from app.api.routes.sinistros import _apply_filters
from app.core.config import settings
from app.db.models import IndicadorMunicipio, MlExecucao, Pessoa, Sinistro
from app.db.session import get_db
from app.schemas.analise import (
    AnaliseResumo,
    ComparacaoCidades,
    FonteDados,
    GrupoVitimas,
    IndicadorCidade,
    ItemDistribuicao,
    MatrizDiaHora,
    PerfilVitimas,
    PontoSerie,
    QualidadeAno,
    QualidadeDados,
    SerieCidade,
    ViaRanking,
)

router = APIRouter(prefix="/analise", tags=["analise"])

_SEM_VALOR = ("", "NAO DISPONIVEL", "NAO INFORMADO")
_GRAVIDADES_PESSOA = {"FATAL": "fatal", "GRAVE": "grave", "LEVE": "leve", "ILESO": "ileso"}
_VEICULOS = {
    "Pedestre": Sinistro.qtd_pedestre, "Bicicleta": Sinistro.qtd_bicicleta,
    "Motocicleta": Sinistro.qtd_motocicleta, "Automóvel": Sinistro.qtd_automovel,
    "Ônibus": Sinistro.qtd_onibus, "Caminhão": Sinistro.qtd_caminhao,
}
_DIMENSOES = {
    "turno": Sinistro.turno, "dia_da_semana": Sinistro.dia_da_semana,
    "tipo_sinistro": Sinistro.tp_sinistro_primario, "tipo_via": Sinistro.tipo_via,
    "tipo_registro": Sinistro.tipo_registro,
}


@dataclass
class Filtros:
    data_inicio: dt.date | None
    data_fim: dt.date | None
    via: str | None
    turno: str | None
    gravidade: str | None
    tipo_registro: str | None
    tp_sinistro_primario: str | None
    tipo_via: str | None
    lat_min: float | None
    lat_max: float | None
    lon_min: float | None
    lon_max: float | None


def filtros(
    data_inicio: dt.date | None = None,
    data_fim: dt.date | None = None,
    via: str | None = Query(None, description="Logradouro exato (sem diferenciar maiúsculas)"),
    turno: str | None = None,
    gravidade: str | None = Query(None, description="Um de: fatal, grave, leve, ileso"),
    tipo_registro: str | None = None,
    tp_sinistro_primario: str | None = None,
    tipo_via: str | None = None,
    lat_min: float | None = None,
    lat_max: float | None = None,
    lon_min: float | None = None,
    lon_max: float | None = None,
) -> Filtros:
    return Filtros(data_inicio, data_fim, via, turno, gravidade, tipo_registro, tp_sinistro_primario,
                   tipo_via, lat_min, lat_max, lon_min, lon_max)


def _filtrar(query: SAQuery, f: Filtros) -> SAQuery:
    query = _apply_filters(
        query, tipo_registro=f.tipo_registro, data_inicio=f.data_inicio, data_fim=f.data_fim,
        gravidade=f.gravidade, tipo_via=f.tipo_via, tipo_local=None, regiao_administrativa=None,
        tp_sinistro_primario=f.tp_sinistro_primario, lat_min=f.lat_min, lat_max=f.lat_max,
        lon_min=f.lon_min, lon_max=f.lon_max, logradouro=f.via, turno=f.turno,
    )
    return query


def _soma(coluna):
    return func.coalesce(func.sum(coluna), 0)


def _conta(condicao):
    return func.coalesce(func.sum(case((condicao, 1), else_=0)), 0)


def _pct(parte: int, total: int) -> float:
    return round(100 * parte / total, 1) if total else 0.0


# ----------------------------------------------------------------------------
# Sinistros
# ----------------------------------------------------------------------------
@router.get("/resumo", response_model=AnaliseResumo)
def resumo(f: Filtros = Depends(filtros), db: Session = Depends(get_db)) -> AnaliseResumo:
    """Totais do recorte: sinistros, óbitos, feridos e período coberto."""
    r = _filtrar(db.query(
        func.count(Sinistro.id), _conta(Sinistro.tipo_registro == "SINISTRO FATAL"),
        _soma(Sinistro.qtd_gravidade_fatal), _soma(Sinistro.qtd_gravidade_grave),
        _soma(Sinistro.qtd_gravidade_leve), _soma(Sinistro.qtd_gravidade_ileso),
        _conta(Sinistro.latitude.is_not(None) & Sinistro.coordenada_generica.is_not(True)),
        _conta(Sinistro.coordenada_generica.is_(True)), func.min(Sinistro.data_sinistro), func.max(Sinistro.data_sinistro),
    ), f).one()
    return AnaliseResumo(sinistros=r[0], sinistros_fatais=r[1], obitos=r[2], feridos_graves=r[3],
                         feridos_leves=r[4], ilesos=r[5], com_coordenada=r[6], coordenada_generica=r[7],
                         data_inicio=r[8], data_fim=r[9])


@router.get("/serie", response_model=list[PontoSerie])
def serie(
    granularidade: str = Query("mes", pattern="^(mes|ano)$"),
    f: Filtros = Depends(filtros),
    db: Session = Depends(get_db),
) -> list[PontoSerie]:
    """Sinistros, óbitos e feridos por mês ou por ano."""
    chaves = [Sinistro.ano_sinistro] + ([Sinistro.mes_sinistro] if granularidade == "mes" else [])
    linhas = (_filtrar(db.query(*chaves, func.count(Sinistro.id), _soma(Sinistro.qtd_gravidade_fatal),
                                _soma(Sinistro.qtd_gravidade_grave), _soma(Sinistro.qtd_gravidade_leve)), f)
              .filter(*(c.is_not(None) for c in chaves)).group_by(*chaves).order_by(*chaves).all())
    pontos = []
    for linha in linhas:
        periodo = f"{linha[0]}-{linha[1]:02d}" if granularidade == "mes" else str(linha[0])
        n, o, g, le = linha[-4:]
        pontos.append(PontoSerie(periodo=periodo, sinistros=n, obitos=o, feridos_graves=g, feridos_leves=le))
    return pontos


@router.get("/distribuicao", response_model=list[ItemDistribuicao])
def distribuicao(
    dimensao: str = Query(..., description="turno, dia_da_semana, hora, tipo_sinistro, tipo_via, tipo_registro ou veiculo"),
    f: Filtros = Depends(filtros),
    db: Session = Depends(get_db),
) -> list[ItemDistribuicao]:
    """Sinistros e óbitos por categoria. Em `veiculo`, um sinistro conta em
    cada tipo envolvido (moto x carro conta nos dois)."""
    if dimensao == "veiculo":
        colunas = []
        for coluna in _VEICULOS.values():
            colunas += [_conta(coluna > 0), _soma(case((coluna > 0, Sinistro.qtd_gravidade_fatal), else_=0))]
        r = _filtrar(db.query(*colunas), f).one()
        itens = [ItemDistribuicao(chave=k, sinistros=r[2 * i], obitos=r[2 * i + 1]) for i, k in enumerate(_VEICULOS)]
        return sorted(itens, key=lambda i: -i.sinistros)
    if dimensao == "hora":
        cont, obitos = Counter(), Counter()
        for hora, fatal in _filtrar(db.query(Sinistro.hora_sinistro, Sinistro.qtd_gravidade_fatal), f):
            if hora is not None:
                cont[hora.hour] += 1
                obitos[hora.hour] += fatal or 0
        return [ItemDistribuicao(chave=f"{h:02d}h", sinistros=cont[h], obitos=obitos[h]) for h in range(24)]
    coluna = _DIMENSOES.get(dimensao)
    if coluna is None:
        raise HTTPException(status_code=422, detail=f"dimensão inválida: {dimensao!r}")
    linhas = (_filtrar(db.query(coluna, func.count(Sinistro.id), _soma(Sinistro.qtd_gravidade_fatal)), f)
              .group_by(coluna).order_by(func.count(Sinistro.id).desc()).all())
    return [ItemDistribuicao(chave=k or "NAO DISPONIVEL", sinistros=n, obitos=o) for k, n, o in linhas]


@router.get("/dia-hora", response_model=MatrizDiaHora)
def dia_hora(f: Filtros = Depends(filtros), db: Session = Depends(get_db)) -> MatrizDiaHora:
    """Sinistros em cada dia da semana (0 = segunda) x hora."""
    matriz = [[0] * 24 for _ in range(7)]
    sem_hora = 0
    for data, hora in _filtrar(db.query(Sinistro.data_sinistro, Sinistro.hora_sinistro), f):
        if data is None or hora is None:
            sem_hora += 1
        else:
            matriz[data.weekday()][hora.hour] += 1
    return MatrizDiaHora(matriz=matriz, sem_hora=sem_hora)


@router.get("/vias", response_model=list[ViaRanking])
def vias(
    limit: int = Query(20, ge=1, le=500),
    f: Filtros = Depends(filtros),
    db: Session = Depends(get_db),
) -> list[ViaRanking]:
    """Logradouros com mais sinistros no recorte."""
    linhas = (_filtrar(db.query(Sinistro.logradouro, func.count(Sinistro.id), _soma(Sinistro.qtd_gravidade_fatal),
                                _soma(Sinistro.qtd_gravidade_grave)), f)
              .filter(Sinistro.logradouro.is_not(None), Sinistro.logradouro.notin_(_SEM_VALOR))
              .group_by(Sinistro.logradouro).order_by(func.count(Sinistro.id).desc()).limit(limit).all())
    return [ViaRanking(via=v, sinistros=n, obitos=o, feridos_graves=g) for v, n, o, g in linhas]


@router.get("/exportar.csv")
def exportar(f: Filtros = Depends(filtros), db: Session = Depends(get_db)) -> StreamingResponse:
    """Os sinistros do recorte em CSV (separador `;`), para quem quiser
    conferir ou analisar fora do site."""
    colunas = ["id_sinistro", "data_sinistro", "hora_sinistro", "dia_da_semana", "turno", "logradouro",
               "numero_logradouro", "tipo_via", "tipo_registro", "tp_sinistro_primario", "latitude", "longitude",
               "qtd_gravidade_fatal", "qtd_gravidade_grave", "qtd_gravidade_leve", "qtd_gravidade_ileso",
               "qtd_pedestre", "qtd_bicicleta", "qtd_motocicleta", "qtd_automovel", "qtd_onibus", "qtd_caminhao"]
    linhas = _filtrar(db.query(*(getattr(Sinistro, c) for c in colunas)), f).order_by(Sinistro.data_sinistro)

    def gerar():
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(colunas)
        for linha in linhas.yield_per(2000):
            w.writerow(["" if v is None else v for v in linha])
            if buf.tell() > 64_000:
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate()
        yield buf.getvalue()

    return StreamingResponse(gerar(), media_type="text/csv; charset=utf-8",
                             headers={"Content-Disposition": 'attachment; filename="sinistros_ribeirao_preto.csv"'})


# ----------------------------------------------------------------------------
# Vítimas
# ----------------------------------------------------------------------------
def _grupos(db: Session, f: Filtros, coluna) -> list[GrupoVitimas]:
    q = db.query(coluna, Pessoa.gravidade_lesao, func.count(Pessoa.id)).join(
        Sinistro, Sinistro.id_sinistro == Pessoa.id_sinistro)
    acumulado: dict[str, Counter] = defaultdict(Counter)
    for chave, gravidade, n in _filtrar(q, f).group_by(coluna, Pessoa.gravidade_lesao):
        acumulado[chave or "NAO DISPONIVEL"][_GRAVIDADES_PESSOA.get(gravidade, "nao_disponivel")] += n
    return [GrupoVitimas(chave=k, total=sum(c.values()), fatal=c["fatal"], grave=c["grave"], leve=c["leve"],
                         ileso=c["ileso"], nao_disponivel=c["nao_disponivel"]) for k, c in acumulado.items()]


def _ordenar(grupos: list[GrupoVitimas], por_chave: bool = False) -> list[GrupoVitimas]:
    sem = [g for g in grupos if g.chave in _SEM_VALOR]
    com = [g for g in grupos if g.chave not in _SEM_VALOR]
    com.sort(key=(lambda g: g.chave) if por_chave else (lambda g: -g.total))
    return com + sem


@router.get("/vitimas", response_model=PerfilVitimas)
def vitimas(f: Filtros = Depends(filtros), db: Session = Depends(get_db)) -> PerfilVitimas:
    """Pessoas envolvidas nos sinistros do recorte, por faixa etária, sexo,
    tipo de vítima e meio de transporte, cada grupo aberto por gravidade."""
    faixa = _ordenar(_grupos(db, f, Pessoa.faixa_etaria), por_chave=True)
    gravidade = Counter()
    for g in faixa:
        gravidade.update({"fatal": g.fatal, "grave": g.grave, "leve": g.leve, "ileso": g.ileso,
                          "nao_disponivel": g.nao_disponivel})
    return PerfilVitimas(
        total=sum(g.total for g in faixa), por_gravidade=dict(gravidade), faixa_etaria=faixa,
        sexo=_ordenar(_grupos(db, f, Pessoa.sexo)), tipo_de_vitima=_ordenar(_grupos(db, f, Pessoa.tipo_de_vitima)),
        modo_transporte=_ordenar(_grupos(db, f, Pessoa.modo_transporte_vitima)),
    )


# ----------------------------------------------------------------------------
# Qualidade dos dados (transparência)
# ----------------------------------------------------------------------------
@router.get("/qualidade", response_model=QualidadeDados)
def qualidade(db: Session = Depends(get_db)) -> QualidadeDados:
    """Preenchimento de cada campo por ano, de onde vêm os dados e o
    diagnóstico da base usada pelos modelos de risco (RENAEST)."""
    por_ano: dict[int, Counter] = defaultdict(Counter)
    colunas = (Sinistro.ano_sinistro, Sinistro.latitude, Sinistro.coordenada_generica, Sinistro.tp_sinistro_primario,
               Sinistro.hora_sinistro, Sinistro.tipo_registro, Sinistro.qtd_gravidade_fatal, Sinistro.qtd_gravidade_grave,
               Sinistro.qtd_gravidade_leve, Sinistro.qtd_gravidade_ileso)
    for ano, lat, generica, tipo, hora, registro, *grav in db.query(*colunas).filter(Sinistro.ano_sinistro.is_not(None)):
        c = por_ano[ano]
        c["n"] += 1
        c["coord"] += lat is not None and not generica
        c["generica"] += bool(generica)
        c["tipo"] += bool(tipo) and tipo not in _SEM_VALOR
        c["hora"] += hora is not None
        c["notificacao"] += registro == "NOTIFICACAO"
        c["classificadas"] += any((g or 0) > 0 for g in grav)

    pessoas = {
        ano: (n, idade, sexo, grav) for ano, n, idade, sexo, grav in db.query(
            Pessoa.ano_sinistro, func.count(Pessoa.id), _conta(Pessoa.idade.is_not(None)),
            _conta(Pessoa.sexo.in_(("MASCULINO", "FEMININO"))),
            _conta(Pessoa.gravidade_lesao.in_(tuple(_GRAVIDADES_PESSOA))),
        ).group_by(Pessoa.ano_sinistro)
    }
    linhas = []
    for ano in sorted(por_ano):
        c = por_ano[ano]
        n_p, idade, sexo, grav = pessoas.get(ano, (0, 0, 0, 0))
        linhas.append(QualidadeAno(
            ano=ano, sinistros=c["n"], pct_coordenada=_pct(c["coord"], c["n"]), coordenada_generica=c["generica"],
            pct_vitimas_classificadas=_pct(c["classificadas"], c["n"]), pct_tipo_informado=_pct(c["tipo"], c["n"]),
            pct_hora=_pct(c["hora"], c["n"]), pct_notificacao=_pct(c["notificacao"], c["n"]), pessoas=n_p,
            pct_idade=_pct(idade, n_p) if n_p else None, pct_sexo=_pct(sexo, n_p) if n_p else None,
            pct_gravidade_pessoa=_pct(grav, n_p) if n_p else None,
        ))

    fontes = [FonteDados(fonte=s, registros=n, data_inicio=a, data_fim=b) for s, n, a, b in db.query(
        Sinistro.source_name, func.count(Sinistro.id), func.min(Sinistro.data_sinistro),
        func.max(Sinistro.data_sinistro)).group_by(Sinistro.source_name).order_by(func.min(Sinistro.data_sinistro))]

    execucao = db.query(MlExecucao).order_by(MlExecucao.id.desc()).first()
    renaest = None
    if execucao is not None:
        renaest = {"fonte": execucao.fonte, "gerado_em": execucao.gerado_em.isoformat(),
                   "qualidade_por_ano": execucao.metricas.get("qualidade_por_ano"),
                   "veiculos": execucao.metricas.get("veiculos"), "resumo_limpeza": execucao.resumo_limpeza}
    return QualidadeDados(por_ano=linhas, fontes=fontes, pessoas=db.query(func.count(Pessoa.id)).scalar(),
                          renaest=renaest)


# ----------------------------------------------------------------------------
# Comparação entre cidades
# ----------------------------------------------------------------------------
def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode().upper()


def _por_100k(valor: int, populacao: int | None) -> float | None:
    return round(valor / populacao * 100_000, 1) if populacao else None


def _indicador(i: IndicadorMunicipio, posicao: int | None = None) -> IndicadorCidade:
    return IndicadorCidade(
        cod_ibge=i.cod_ibge, municipio=i.municipio, populacao=i.populacao, sinistros=i.sinistros,
        sinistros_fatais=i.sinistros_fatais, notificacoes=i.notificacoes, obitos=i.obitos,
        feridos_graves=i.feridos_graves, feridos_leves=i.feridos_leves,
        obitos_100k=_por_100k(i.obitos, i.populacao), graves_100k=_por_100k(i.feridos_graves, i.populacao),
        sinistros_100k=_por_100k(i.sinistros, i.populacao), posicao_obitos=posicao,
    )


def _cod_referencia(db: Session) -> int | None:
    alvo = _sem_acento(settings.municipio_alvo)
    for cod, nome in db.query(IndicadorMunicipio.cod_ibge, IndicadorMunicipio.municipio).distinct():
        if _sem_acento(nome) == alvo:
            return cod
    return None


@router.get("/municipios", response_model=ComparacaoCidades)
def municipios(
    ano: int | None = Query(None, description="Padrão: o último ano com os 12 meses"),
    populacao_min: int = Query(300_000, ge=0, description="Só cidades a partir desta população"),
    db: Session = Depends(get_db),
) -> ComparacaoCidades:
    """Indicadores por 100 mil habitantes das cidades de SP de porte
    parecido, ordenados por óbitos (o indicador mais comparável: o volume de
    sinistros não fatais depende de quanto cada cidade notifica)."""
    anos = dict(db.query(IndicadorMunicipio.ano, func.max(IndicadorMunicipio.meses_com_dados))
                .group_by(IndicadorMunicipio.ano).all())
    if not anos:
        raise HTTPException(status_code=404, detail="Indicadores por município não carregados (rode scripts/carregar_infosiga.py).")
    if ano is None:
        ano = max(a for a, m in anos.items() if m == 12)
    if ano not in anos:
        raise HTTPException(status_code=404, detail=f"Sem dados de {ano}.")

    linhas = db.query(IndicadorMunicipio).filter(IndicadorMunicipio.ano == ano).all()
    grupo = sorted((i for i in linhas if (i.populacao or 0) >= populacao_min),
                   key=lambda i: -(i.obitos / i.populacao) if i.populacao else 0)
    cod_ref = _cod_referencia(db)
    itens = [_indicador(i, pos) for pos, i in enumerate(grupo, start=1)]
    referencia = next((x for x in itens if x.cod_ibge == cod_ref), None)
    if referencia is None and cod_ref is not None:
        ref = next((i for i in linhas if i.cod_ibge == cod_ref), None)
        referencia = _indicador(ref) if ref else None
    return ComparacaoCidades(ano=ano, meses_com_dados=anos[ano], anos_disponiveis=sorted(anos),
                             populacao_min=populacao_min, referencia=referencia, municipios=itens)


@router.get("/municipios/serie", response_model=list[SerieCidade])
def municipios_serie(
    cod_ibge: list[int] = Query(..., description="Um ou mais códigos IBGE (repita o parâmetro)"),
    db: Session = Depends(get_db),
) -> list[SerieCidade]:
    """Evolução anual dos indicadores por 100 mil habitantes das cidades pedidas."""
    linhas = (db.query(IndicadorMunicipio).filter(IndicadorMunicipio.cod_ibge.in_(cod_ibge))
              .order_by(IndicadorMunicipio.ano).all())
    por_cidade: dict[int, list] = defaultdict(list)
    for i in linhas:
        por_cidade[i.cod_ibge].append(i)
    return [SerieCidade(cod_ibge=cod, municipio=itens[0].municipio, anos=[
        {"ano": i.ano, "meses_com_dados": i.meses_com_dados, "populacao": i.populacao, "obitos": i.obitos,
         "obitos_100k": _por_100k(i.obitos, i.populacao), "graves_100k": _por_100k(i.feridos_graves, i.populacao),
         "sinistros_100k": _por_100k(i.sinistros, i.populacao)} for i in itens])
        for cod, itens in por_cidade.items()]
