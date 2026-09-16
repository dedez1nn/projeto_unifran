import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict


class SinistroOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_name: str
    source_row_id: str
    id_sinistro: int | None
    tipo_registro: str | None
    data_sinistro: dt.date | None
    hora_sinistro: dt.time | None
    dia_da_semana: str | None
    turno: str | None
    logradouro: str | None
    numero_logradouro: str | None
    tipo_via: str | None
    tipo_local: str | None
    latitude: float | None
    longitude: float | None
    municipio: str | None
    regiao_administrativa: str | None
    tp_sinistro_primario: str | None
    qtd_pedestre: int | None
    qtd_bicicleta: int | None
    qtd_motocicleta: int | None
    qtd_automovel: int | None
    qtd_onibus: int | None
    qtd_caminhao: int | None
    qtd_gravidade_fatal: int | None
    qtd_gravidade_grave: int | None
    qtd_gravidade_leve: int | None
    qtd_gravidade_ileso: int | None
    tp_sinistro_atrop_pedestre: bool
    tp_sinistro_colisao_frontal: bool
    tp_sinistro_colisao_traseira: bool
    tp_sinistro_colisao_lateral: bool
    tp_sinistro_capotamento: bool
    tp_sinistro_engavetamento: bool
    tp_sinistro_tombamento: bool
    source_file: str | None
    ingested_at: dt.datetime


class SinistroFeatureProperties(BaseModel):
    id: int
    data: dt.date | None
    hora: dt.time | None
    turno: str | None
    dia_da_semana: str | None
    logradouro: str | None
    tipo_via: str | None
    tipo_local: str | None
    regiao_administrativa: str | None
    tipo_registro: str | None
    tp_sinistro_primario: str | None
    qtd_gravidade_fatal: int | None
    qtd_gravidade_grave: int | None
    qtd_gravidade_leve: int | None
    qtd_gravidade_ileso: int | None


class GeoJSONPoint(BaseModel):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float]  # [longitude, latitude], ordem padrão GeoJSON


class SinistroFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: GeoJSONPoint
    properties: SinistroFeatureProperties


class SinistroFeatureCollection(BaseModel):
    """Dados de sinistros geocodificados em GeoJSON puro, para o frontend
    renderizar seu próprio mapa (Leaflet, Mapbox GL etc.) — ver `GET
    /sinistros/geojson`.
    """

    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[SinistroFeature]


class IngestionSummary(BaseModel):
    source_file: str
    total_rows: int
    inserted: int
    updated: int
    skipped_other_municipio: int
    skipped_invalid: int
    colunas_nao_mapeadas: list[str] = []
    avisos: list[str] = []
