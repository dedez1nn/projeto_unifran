import datetime as dt
from typing import Literal

from pydantic import BaseModel, ConfigDict

NivelRisco = Literal["ALTO", "MEDIO", "BAIXO"]
Veiculo = Literal["moto", "carro", "caminhao", "onibus"]


class ZonaProperties(BaseModel):
    celula: str
    nivel_risco: NivelRisco
    acidentes_esperados: float
    acidentes_12m: float
    acidentes_historico: float
    obitos_historico: float
    rua_principal: str | None
    em_alta: bool
    tendencia_razao: float | None
    janela_previsao: str
    # Preenchidos só com `?veiculo=`: aí `acidentes_esperados` e `nivel_risco`
    # passam a ser os dos acidentes envolvendo aquela categoria.
    veiculo: Veiculo | None = None
    fracao_veiculo: float | None = None


class ZonaPolygon(BaseModel):
    type: Literal["Polygon"] = "Polygon"
    coordinates: list[list[list[float]]]


class ZonaFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: ZonaPolygon
    properties: ZonaProperties


class ZonaFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[ZonaFeature]


class VeiculoOut(BaseModel):
    veiculo: Veiculo
    # fração dos acidentes com tipo informado que envolvem a categoria
    fracao_cidade: float
    acidentes_esperados: float


class VeiculosOut(BaseModel):
    # fração dos acidentes desde 2023 com tipo de veículo informado
    cobertura_tipo_veiculo: float
    veiculos: list[VeiculoOut]


class ViaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    via: str
    acidentes_esperados: float
    acidentes_historico: float
    nivel_risco: NivelRisco
    lat: float
    lon: float


class PontoCriticoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    lat: float
    lon: float
    raio_m: float
    n_acidentes_fatais: int
    n_obitos: int
    rua_principal: str | None
    primeiro: dt.date
    ultimo: dt.date


class PrevisaoMensalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    mes: str
    real: float | None
    previsto: float
    limite_inferior: float | None
    limite_superior: float | None
    futuro: bool


class PerfilHorarioOut(BaseModel):
    escopo: str
    # matriz[dia_semana][hora], dia 0 = segunda; soma 1 na matriz inteira
    matriz: list[list[float]]


class SimulacaoOut(BaseModel):
    via: str
    dia_semana: int
    horas: list[int]
    acidentes_esperados_ano: float
    acidentes_esperados_janela: float
    intensidade: float
    indice: int
    nivel_risco: NivelRisco
    horas_pico_no_dia: list[int]
    fatores: list[str]
    janela_previsao: str


class RiscoAgoraItem(BaseModel):
    via: str
    indice: int
    nivel_risco: NivelRisco
    acidentes_esperados_ano: float
    intensidade: float


class ModeloOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    gerado_em: dt.datetime
    fonte: str
    modelo_ocorrencia: str
    janela_previsao: str
    metricas: dict
    resumo_limpeza: dict
