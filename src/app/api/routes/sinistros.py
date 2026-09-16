import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Query as SAQuery
from sqlalchemy.orm import Session

from app.db.models import Sinistro
from app.db.session import get_db
from app.schemas.sinistro import (
    GeoJSONPoint,
    SinistroFeature,
    SinistroFeatureCollection,
    SinistroFeatureProperties,
    SinistroOpcoes,
    SinistroOut,
)

router = APIRouter(prefix="/sinistros", tags=["sinistros"])

_GRAVIDADE_COLUNAS = {
    "fatal": Sinistro.qtd_gravidade_fatal,
    "grave": Sinistro.qtd_gravidade_grave,
    "leve": Sinistro.qtd_gravidade_leve,
    "ileso": Sinistro.qtd_gravidade_ileso,
}


def _apply_filters(
    query: SAQuery,
    *,
    tipo_registro: str | None,
    data_inicio: dt.date | None,
    data_fim: dt.date | None,
    gravidade: str | None,
    tipo_via: str | None,
    tipo_local: str | None,
    regiao_administrativa: str | None,
    tp_sinistro_primario: str | None,
    lat_min: float | None,
    lat_max: float | None,
    lon_min: float | None,
    lon_max: float | None,
) -> SAQuery:
    """Filtros compartilhados entre `GET /sinistros` e `GET /sinistros/geojson`
    — mantém as duas rotas de consulta (dados tabulares e dados de mapa)
    consistentes entre si.
    """
    if tipo_registro:
        query = query.filter(Sinistro.tipo_registro == tipo_registro)
    if data_inicio:
        query = query.filter(Sinistro.data_sinistro >= data_inicio)
    if data_fim:
        query = query.filter(Sinistro.data_sinistro <= data_fim)
    if gravidade:
        coluna = _GRAVIDADE_COLUNAS.get(gravidade)
        if coluna is None:
            raise HTTPException(
                status_code=400,
                detail=f"gravidade inválida: {gravidade!r}. Use um de {sorted(_GRAVIDADE_COLUNAS)}",
            )
        query = query.filter(coluna > 0)
    if tipo_via:
        query = query.filter(Sinistro.tipo_via == tipo_via)
    if tipo_local:
        query = query.filter(Sinistro.tipo_local == tipo_local)
    if regiao_administrativa:
        query = query.filter(Sinistro.regiao_administrativa == regiao_administrativa)
    if tp_sinistro_primario:
        query = query.filter(Sinistro.tp_sinistro_primario == tp_sinistro_primario)
    if lat_min is not None:
        query = query.filter(Sinistro.latitude >= lat_min)
    if lat_max is not None:
        query = query.filter(Sinistro.latitude <= lat_max)
    if lon_min is not None:
        query = query.filter(Sinistro.longitude >= lon_min)
    if lon_max is not None:
        query = query.filter(Sinistro.longitude <= lon_max)
    return query


@router.get("", response_model=list[SinistroOut])
def list_sinistros(
    tipo_registro: str | None = None,
    data_inicio: dt.date | None = None,
    data_fim: dt.date | None = None,
    gravidade: str | None = Query(
        default=None, description="Um de: fatal, grave, leve, ileso"
    ),
    tipo_via: str | None = None,
    tipo_local: str | None = None,
    regiao_administrativa: str | None = None,
    tp_sinistro_primario: str | None = None,
    lat_min: float | None = None,
    lat_max: float | None = None,
    lon_min: float | None = None,
    lon_max: float | None = None,
    limit: int = Query(default=100, le=1000),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
) -> list[Sinistro]:
    """Consulta paginada dos sinistros ingeridos — pensada para o time de
    análise de dados puxar lotes conforme a base cresce, sem acesso direto ao
    banco. Além dos filtros por atributo, aceita uma bounding box
    (`lat_min`/`lat_max`/`lon_min`/`lon_max`) para restringir a uma área
    geográfica.
    """
    query = _apply_filters(
        db.query(Sinistro),
        tipo_registro=tipo_registro,
        data_inicio=data_inicio,
        data_fim=data_fim,
        gravidade=gravidade,
        tipo_via=tipo_via,
        tipo_local=tipo_local,
        regiao_administrativa=regiao_administrativa,
        tp_sinistro_primario=tp_sinistro_primario,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
    )

    return (
        query.order_by(Sinistro.data_sinistro, Sinistro.id)
        .offset(offset)
        .limit(limit)
        .all()
    )


@router.get("/geojson", response_model=SinistroFeatureCollection)
def sinistros_geojson(
    tipo_registro: str | None = None,
    data_inicio: dt.date | None = None,
    data_fim: dt.date | None = None,
    gravidade: str | None = Query(
        default=None, description="Um de: fatal, grave, leve, ileso"
    ),
    tipo_via: str | None = None,
    tipo_local: str | None = None,
    regiao_administrativa: str | None = None,
    tp_sinistro_primario: str | None = None,
    lat_min: float | None = None,
    lat_max: float | None = None,
    lon_min: float | None = None,
    lon_max: float | None = None,
    limit: int = Query(default=5000, le=20000),
    db: Session = Depends(get_db),
) -> SinistroFeatureCollection:
    """Sinistros geocodificados em GeoJSON puro (FeatureCollection de pontos),
    para o frontend renderizar seu próprio mapa (Leaflet, Mapbox GL etc.) sem
    depender da página HTML pronta de `GET /mapa`. Aceita os mesmos filtros
    de `GET /sinistros`, incluindo bounding box, para pedir só o recorte
    relevante (ex: o viewport atual do mapa) em vez da base inteira.
    """
    query = _apply_filters(
        db.query(Sinistro).filter(
            Sinistro.latitude.is_not(None), Sinistro.longitude.is_not(None)
        ),
        tipo_registro=tipo_registro,
        data_inicio=data_inicio,
        data_fim=data_fim,
        gravidade=gravidade,
        tipo_via=tipo_via,
        tipo_local=tipo_local,
        regiao_administrativa=regiao_administrativa,
        tp_sinistro_primario=tp_sinistro_primario,
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
    )
    rows = query.order_by(Sinistro.data_sinistro, Sinistro.id).limit(limit).all()

    return SinistroFeatureCollection(
        features=[
            SinistroFeature(
                geometry=GeoJSONPoint(coordinates=(r.longitude, r.latitude)),
                properties=SinistroFeatureProperties(
                    id=r.id,
                    data=r.data_sinistro,
                    hora=r.hora_sinistro,
                    turno=r.turno,
                    dia_da_semana=r.dia_da_semana,
                    logradouro=r.logradouro,
                    tipo_via=r.tipo_via,
                    tipo_local=r.tipo_local,
                    regiao_administrativa=r.regiao_administrativa,
                    tipo_registro=r.tipo_registro,
                    tp_sinistro_primario=r.tp_sinistro_primario,
                    qtd_gravidade_fatal=r.qtd_gravidade_fatal,
                    qtd_gravidade_grave=r.qtd_gravidade_grave,
                    qtd_gravidade_leve=r.qtd_gravidade_leve,
                    qtd_gravidade_ileso=r.qtd_gravidade_ileso,
                ),
            )
            for r in rows
        ]
    )


def _distinct_values(db: Session, column) -> list:
    rows = (
        db.query(column)
        .filter(column.is_not(None), column != "")
        .distinct()
        .order_by(column)
        .all()
    )
    return [v for (v,) in rows]


@router.get("/opcoes", response_model=SinistroOpcoes)
def sinistros_opcoes(db: Session = Depends(get_db)) -> SinistroOpcoes:
    """Valores distintos presentes na base para cada campo filtrável, para o
    frontend montar os controles de filtro (selects, checkboxes) sem
    hardcodar nem adivinhar as opções válidas.
    """
    return SinistroOpcoes(
        tipo_registro=_distinct_values(db, Sinistro.tipo_registro),
        tipo_via=_distinct_values(db, Sinistro.tipo_via),
        tipo_local=_distinct_values(db, Sinistro.tipo_local),
        regiao_administrativa=_distinct_values(db, Sinistro.regiao_administrativa),
        tp_sinistro_primario=_distinct_values(db, Sinistro.tp_sinistro_primario),
        gravidade=sorted(_GRAVIDADE_COLUNAS),
        anos=_distinct_values(db, Sinistro.ano_sinistro),
    )


@router.get("/{id}", response_model=SinistroOut)
def get_sinistro(id: int, db: Session = Depends(get_db)) -> Sinistro:
    obj = db.get(Sinistro, id)
    if obj is None:
        raise HTTPException(status_code=404, detail="Sinistro não encontrado")
    return obj
