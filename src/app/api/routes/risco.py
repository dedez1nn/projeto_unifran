from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.models import (
    MlExecucao,
    RiscoCelula,
    RiscoCelulaVeiculo,
    RiscoPerfilHorario,
    RiscoPontoCritico,
    RiscoPrevisaoMensal,
    RiscoVia,
)
from app.db.session import get_db
from app.schemas.risco import (
    ModeloOut,
    NivelRisco,
    PerfilHorarioOut,
    PontoCriticoOut,
    PrevisaoMensalOut,
    RiscoAgoraItem,
    SimulacaoOut,
    Veiculo,
    VeiculoOut,
    VeiculosOut,
    ViaOut,
    ZonaFeature,
    ZonaFeatureCollection,
    ZonaPolygon,
    ZonaProperties,
)
from app.services import risco_service

router = APIRouter(prefix="/risco", tags=["risco"])

ESCOPO_CIDADE = "__cidade__"
_SEM_MODELO = "Nenhum modelo de risco publicado ainda (rode scripts/treinar_risco.py)."


def _execucao_atual(db: Session) -> MlExecucao:
    execucao = db.query(MlExecucao).order_by(MlExecucao.id.desc()).first()
    if execucao is None:
        raise HTTPException(status_code=404, detail=_SEM_MODELO)
    return execucao


def _fracoes(db: Session, escopo: str) -> dict[tuple[int, int], float]:
    linhas = db.query(RiscoPerfilHorario).filter(RiscoPerfilHorario.escopo == escopo).all()
    return {(p.dia_semana, p.hora): p.fracao for p in linhas}


@router.get("/modelo", response_model=ModeloOut)
def modelo(db: Session = Depends(get_db)) -> MlExecucao:
    """Versão publicada do modelo: quando foi gerada, qual venceu o backtest
    e as métricas dele contra os baselines (média histórica etc.)."""
    return _execucao_atual(db)


@router.get("/zonas", response_model=ZonaFeatureCollection)
def zonas(
    nivel: list[NivelRisco] | None = Query(None, description="Um ou mais níveis (repita o parâmetro)"),
    em_alta: bool | None = Query(None, description="Só zonas em alta (ou só as que não estão)"),
    veiculo: Veiculo | None = Query(None, description="Previsão só dos acidentes envolvendo a categoria"),
    celula: str | None = Query(None, description="Uma célula específica (ficha da zona)"),
    db: Session = Depends(get_db),
) -> ZonaFeatureCollection:
    """Células de ~550 m com a previsão de acidentes para os próximos 12
    meses, como polígonos GeoJSON prontos para o mapa. Com `veiculo`, a
    previsão e o nível passam a ser os dos acidentes envolvendo aquela
    categoria (e `nivel` filtra por esse nível)."""
    if veiculo is None:
        query = db.query(RiscoCelula)
        if nivel:
            query = query.filter(RiscoCelula.nivel_risco.in_(nivel))
        pares = [(c, None) for c in query]
    else:
        query = (db.query(RiscoCelula, RiscoCelulaVeiculo)
                 .join(RiscoCelulaVeiculo, RiscoCelulaVeiculo.celula == RiscoCelula.celula)
                 .filter(RiscoCelulaVeiculo.veiculo == veiculo))
        if nivel:
            query = query.filter(RiscoCelulaVeiculo.nivel_risco.in_(nivel))
        pares = query.all()
    if em_alta is not None:
        pares = [(c, v) for c, v in pares if c.em_alta == em_alta]
    if celula is not None:
        pares = [(c, v) for c, v in pares if c.celula == celula]

    features = []
    for c, v in pares:
        props = ZonaProperties.model_validate(c, from_attributes=True)
        if v is not None:
            props = props.model_copy(update={"acidentes_esperados": v.acidentes_esperados, "nivel_risco": v.nivel_risco,
                                             "veiculo": v.veiculo, "fracao_veiculo": v.fracao})
        features.append(ZonaFeature(geometry=ZonaPolygon(coordinates=risco_service.quadrado(c.lat, c.lon, c.tamanho)),
                                    properties=props))
    features.sort(key=lambda f: f.properties.acidentes_esperados, reverse=True)
    return ZonaFeatureCollection(features=features)


@router.get("/veiculos", response_model=VeiculosOut)
def veiculos(db: Session = Depends(get_db)) -> VeiculosOut:
    """Categorias disponíveis para `GET /risco/zonas?veiculo=`, com a fração
    de acidentes que envolvem cada uma. 404 se o treino não recebeu a tabela
    de veículos."""
    resumo = _execucao_atual(db).metricas.get("veiculos")
    if not resumo:
        raise HTTPException(status_code=404, detail="O modelo publicado não tem previsão por veículo.")
    totais = dict(db.query(RiscoCelulaVeiculo.veiculo, func.sum(RiscoCelulaVeiculo.acidentes_esperados))
                  .group_by(RiscoCelulaVeiculo.veiculo).all())
    return VeiculosOut(
        cobertura_tipo_veiculo=resumo["cobertura_tipo_veiculo"],
        veiculos=[VeiculoOut(veiculo=k, fracao_cidade=f, acidentes_esperados=totais.get(k, 0.0))
                  for k, f in sorted(resumo["fracao_cidade"].items(), key=lambda kv: -kv[1])],
    )


@router.get("/vias", response_model=list[ViaOut])
def vias(limit: int = Query(300, ge=1, le=1000), db: Session = Depends(get_db)) -> list[RiscoVia]:
    """Vias ordenadas pelos acidentes previstos nos próximos 12 meses.
    Alimenta o seletor de via da simulação e o ranking do site."""
    return db.query(RiscoVia).order_by(RiscoVia.acidentes_esperados.desc()).limit(limit).all()


@router.get("/pontos-criticos", response_model=list[PontoCriticoOut])
def pontos_criticos(limit: int = Query(20, ge=1, le=200), db: Session = Depends(get_db)) -> list[RiscoPontoCritico]:
    """Aglomerados de acidentes com óbito (raio de até ~150 m), do mais
    para o menos letal."""
    return (db.query(RiscoPontoCritico)
            .order_by(RiscoPontoCritico.n_obitos.desc(), RiscoPontoCritico.n_acidentes_fatais.desc())
            .limit(limit).all())


@router.get("/previsao-mensal", response_model=list[PrevisaoMensalOut])
def previsao_mensal(db: Session = Depends(get_db)) -> list[RiscoPrevisaoMensal]:
    """Total mensal da cidade: histórico real + próximos 12 meses previstos
    com intervalo de 95%."""
    return db.query(RiscoPrevisaoMensal).order_by(RiscoPrevisaoMensal.mes).all()


@router.get("/perfil-horario", response_model=PerfilHorarioOut)
def perfil_horario(via: str | None = None, db: Session = Depends(get_db)) -> PerfilHorarioOut:
    """Fração dos acidentes em cada dia da semana x hora, da cidade (sem
    `via`) ou de uma via do ranking."""
    escopo = via or ESCOPO_CIDADE
    fracoes = _fracoes(db, escopo)
    if not fracoes:
        raise HTTPException(status_code=404, detail=f"Sem perfil horário para {escopo!r}.")
    return PerfilHorarioOut(escopo=escopo, matriz=[[fracoes.get((d, h), 0.0) for h in range(24)] for d in range(7)])


@router.get("/simular", response_model=SimulacaoOut)
def simular(
    via: str,
    dia_semana: int = Query(..., ge=0, le=6, description="0 = segunda ... 6 = domingo"),
    horas: list[int] = Query(..., description="Horas da janela, 0-23 (repita o parâmetro)"),
    db: Session = Depends(get_db),
) -> SimulacaoOut:
    """Risco de uma via num dia da semana e janela de horas: acidentes
    esperados por ano naquela janela e índice 0-100 (ver
    `services/risco_service.py` para a escala)."""
    if any(not 0 <= h <= 23 for h in horas):
        raise HTTPException(status_code=422, detail="horas devem estar entre 0 e 23")
    execucao = _execucao_atual(db)
    registro = db.query(RiscoVia).filter(RiscoVia.via == via).first()
    if registro is None:
        raise HTTPException(status_code=404, detail=f"Via {via!r} não está no ranking (ver GET /risco/vias).")
    m = execucao.metricas
    resultado = risco_service.simular(
        via=via, acidentes_ano=registro.acidentes_esperados, fracoes=_fracoes(db, via),
        dia_semana=dia_semana, horas=horas, quantis=m["quantis_taxa_hora"], nivel_via=registro.nivel_risco,
    )
    return SimulacaoOut(**resultado, janela_previsao=execucao.janela_previsao)


@router.get("/agora", response_model=list[RiscoAgoraItem])
def agora(
    dia_semana: int = Query(..., ge=0, le=6),
    hora: int = Query(..., ge=0, le=23),
    limit: int = Query(5, ge=1, le=50),
    db: Session = Depends(get_db),
) -> list[RiscoAgoraItem]:
    """As vias de maior risco num dia/hora específicos (o painel "Risco
    agora" passa o dia e a hora do relógio de quem está vendo)."""
    m = _execucao_atual(db).metricas
    fracoes = dict(
        db.query(RiscoPerfilHorario.escopo, RiscoPerfilHorario.fracao)
        .filter(RiscoPerfilHorario.dia_semana == dia_semana, RiscoPerfilHorario.hora == hora,
                RiscoPerfilHorario.escopo != ESCOPO_CIDADE)
        .all()
    )
    itens = []
    for v in db.query(RiscoVia).all():
        fracao = fracoes.get(v.via, 0.0)
        indice = risco_service.indice_risco(v.acidentes_esperados * fracao, m["quantis_taxa_hora"])
        itens.append(RiscoAgoraItem(
            via=v.via, indice=indice, nivel_risco=risco_service.nivel_por_indice(indice),
            acidentes_esperados_ano=v.acidentes_esperados, intensidade=fracao * 168,
        ))
    itens.sort(key=lambda i: (i.indice, i.acidentes_esperados_ano * i.intensidade), reverse=True)
    return itens[:limit]
