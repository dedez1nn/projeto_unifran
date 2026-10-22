import datetime as dt

from pydantic import BaseModel


class AnaliseResumo(BaseModel):
    sinistros: int
    sinistros_fatais: int
    obitos: int
    feridos_graves: int
    feridos_leves: int
    ilesos: int
    com_coordenada: int  # sem contar as coordenadas genéricas do geocodificador
    coordenada_generica: int
    data_inicio: dt.date | None
    data_fim: dt.date | None


class PontoSerie(BaseModel):
    periodo: str  # "2025-03" (mês) ou "2025" (ano)
    sinistros: int
    obitos: int
    feridos_graves: int
    feridos_leves: int


class ItemDistribuicao(BaseModel):
    chave: str
    sinistros: int
    obitos: int


class MatrizDiaHora(BaseModel):
    # matriz[dia_semana][hora], dia 0 = segunda; contagem de sinistros
    matriz: list[list[int]]
    sem_hora: int


class ViaRanking(BaseModel):
    via: str
    sinistros: int
    obitos: int
    feridos_graves: int


class GrupoVitimas(BaseModel):
    chave: str
    total: int
    fatal: int
    grave: int
    leve: int
    ileso: int
    nao_disponivel: int


class PerfilVitimas(BaseModel):
    total: int
    por_gravidade: dict[str, int]
    faixa_etaria: list[GrupoVitimas]
    sexo: list[GrupoVitimas]
    tipo_de_vitima: list[GrupoVitimas]
    modo_transporte: list[GrupoVitimas]


class QualidadeAno(BaseModel):
    ano: int
    sinistros: int
    pct_coordenada: float
    coordenada_generica: int
    pct_vitimas_classificadas: float
    pct_tipo_informado: float
    pct_hora: float
    pct_notificacao: float
    pessoas: int
    pct_idade: float | None
    pct_sexo: float | None
    pct_gravidade_pessoa: float | None


class FonteDados(BaseModel):
    fonte: str
    registros: int
    data_inicio: dt.date | None
    data_fim: dt.date | None


class QualidadeDados(BaseModel):
    por_ano: list[QualidadeAno]
    fontes: list[FonteDados]
    pessoas: int
    renaest: dict | None  # diagnóstico do treino dos modelos de risco (`ml_execucoes`), se houver


class IndicadorCidade(BaseModel):
    cod_ibge: int
    municipio: str
    populacao: int | None
    sinistros: int
    sinistros_fatais: int
    notificacoes: int
    obitos: int
    feridos_graves: int
    feridos_leves: int
    obitos_100k: float | None
    graves_100k: float | None
    sinistros_100k: float | None
    posicao_obitos: int | None


class ComparacaoCidades(BaseModel):
    ano: int
    meses_com_dados: int
    anos_disponiveis: list[int]
    populacao_min: int
    referencia: IndicadorCidade | None
    municipios: list[IndicadorCidade]


class SerieCidade(BaseModel):
    cod_ibge: int
    municipio: str
    anos: list[dict]
