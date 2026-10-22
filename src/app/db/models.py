import datetime as dt

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base

ROLE_ADMIN = "admin"
ROLE_USER = "user"


class User(Base):
    """Conta cadastrada via `POST /auth/register`, sempre criada com papel
    `user` (nunca `admin`, para o cadastro público não conseguir se
    auto-promover). O admin "raiz" continua vindo de `settings`
    (`ADMIN_USERNAME`/`ADMIN_PASSWORD_HASH`), não desta tabela. Ver
    `core/security.py` e `api/routes/auth.py`.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(150), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default=ROLE_USER)
    name: Mapped[str | None] = mapped_column(String(150))
    email: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow
    )


class Sinistro(Base):
    """Registro de sinistro de trânsito, escopo Ribeirão Preto-SP.

    A ingestão aceita fontes heterogêneas (formato oficial INFOSIGA e
    quaisquer outros CSVs de sinistros, ver `services/adapters.py`), então a
    chave de upsert não é mais `id_sinistro` (que só existe nalgumas
    fontes) — é `(source_name, source_row_id)`: cada fonte declara sua
    própria noção de "linha única". `id_sinistro` continua existindo como
    coluna comum (preenchida quando a fonte tem esse campo), só deixou de
    ser a chave primária.
    """

    __tablename__ = "sinistros"
    __table_args__ = (
        UniqueConstraint(
            "source_name", "source_row_id", name="uq_sinistro_source_row"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Proveniência + chave natural da linha na fonte (ver docstring acima).
    source_name: Mapped[str] = mapped_column(String(50), index=True)
    source_row_id: Mapped[str] = mapped_column(String(120), index=True)

    id_sinistro: Mapped[int | None] = mapped_column(Integer, index=True)
    tipo_registro: Mapped[str | None] = mapped_column(String(50))

    data_sinistro: Mapped[dt.date | None] = mapped_column(Date)
    ano_sinistro: Mapped[int | None] = mapped_column(Integer)
    mes_sinistro: Mapped[int | None] = mapped_column(Integer)
    dia_sinistro: Mapped[int | None] = mapped_column(Integer)
    hora_sinistro: Mapped[dt.time | None] = mapped_column(Time)
    ano_mes_sinistro: Mapped[str | None] = mapped_column(String(10))
    dia_da_semana: Mapped[str | None] = mapped_column(String(20))
    turno: Mapped[str | None] = mapped_column(String(20))

    logradouro: Mapped[str | None] = mapped_column(String(255))
    numero_logradouro: Mapped[str | None] = mapped_column(String(20))
    tipo_via: Mapped[str | None] = mapped_column(String(50))
    tipo_local: Mapped[str | None] = mapped_column(String(50))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    cod_ibge: Mapped[int | None] = mapped_column(Integer)
    municipio: Mapped[str | None] = mapped_column(String(100), index=True)
    regiao_administrativa: Mapped[str | None] = mapped_column(String(100))
    administracao: Mapped[str | None] = mapped_column(String(50))
    conservacao: Mapped[str | None] = mapped_column(String(50))
    circunscricao: Mapped[str | None] = mapped_column(String(50))

    tp_sinistro_primario: Mapped[str | None] = mapped_column(String(50))

    qtd_pedestre: Mapped[int | None] = mapped_column(Integer)
    qtd_bicicleta: Mapped[int | None] = mapped_column(Integer)
    qtd_motocicleta: Mapped[int | None] = mapped_column(Integer)
    qtd_automovel: Mapped[int | None] = mapped_column(Integer)
    qtd_onibus: Mapped[int | None] = mapped_column(Integer)
    qtd_caminhao: Mapped[int | None] = mapped_column(Integer)
    qtd_veic_outros: Mapped[int | None] = mapped_column(Integer)
    qtd_veic_nao_disponivel: Mapped[int | None] = mapped_column(Integer)

    qtd_gravidade_fatal: Mapped[int | None] = mapped_column(Integer)
    qtd_gravidade_grave: Mapped[int | None] = mapped_column(Integer)
    qtd_gravidade_leve: Mapped[int | None] = mapped_column(Integer)
    qtd_gravidade_ileso: Mapped[int | None] = mapped_column(Integer)
    qtd_gravidade_nao_disponivel: Mapped[int | None] = mapped_column(Integer)

    tp_sinistro_atrop_pedestre: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_atrop_vitima_fora_veic: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_colisao_frontal: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_colisao_traseira: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_colisao_lateral: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_colisao_transversal: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_colisao_outros: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_choque: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_atrop_animal: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_capotamento: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_engavetamento: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_tombamento: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_outros: Mapped[bool] = mapped_column(Boolean, default=False)
    tp_sinistro_nao_disponivel: Mapped[bool] = mapped_column(Boolean, default=False)

    # Linha original crua (todas as colunas do CSV-fonte, mapeadas ou não) —
    # nenhum dado se perde mesmo quando o formato não é reconhecido.
    raw_data: Mapped[dict | None] = mapped_column(JSON)

    # Metadados de proveniência: importam porque a ingestão é repetida ao longo
    # do tempo (novos arquivos), então precisamos rastrear de onde cada linha veio.
    source_file: Mapped[str | None] = mapped_column(String(255))
    ingested_at: Mapped[dt.datetime] = mapped_column(
        DateTime, default=dt.datetime.utcnow
    )


# ----------------------------------------------------------------------------
# Modelos de risco: tabelas publicadas pelo treino (`scripts/treinar_risco.py`,
# código em `src/ml/`) e só lidas pela API (`api/routes/risco.py`). Cada
# publicação substitui o conteúdo inteiro de todas elas numa transação, e
# `MlExecucao` guarda o histórico de quando/como cada versão foi gerada.
# ----------------------------------------------------------------------------
class RiscoCelula(Base):
    """Célula de ~550 m com a previsão de acidentes para os próximos 12
    meses. `lat`/`lon` são o centro; o quadrado vai de ±`tamanho`/2."""

    __tablename__ = "risco_celulas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    celula: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    tamanho: Mapped[float] = mapped_column(Float)
    acidentes_esperados: Mapped[float] = mapped_column(Float)
    acidentes_12m: Mapped[float] = mapped_column(Float)
    acidentes_historico: Mapped[float] = mapped_column(Float)
    obitos_historico: Mapped[float] = mapped_column(Float)
    nivel_risco: Mapped[str] = mapped_column(String(10), index=True)
    rua_principal: Mapped[str | None] = mapped_column(String(255))
    tendencia_razao: Mapped[float | None] = mapped_column(Float)
    em_alta: Mapped[bool] = mapped_column(Boolean, default=False)
    janela_previsao: Mapped[str] = mapped_column(String(30))


class RiscoCelulaVeiculo(Base):
    """Previsão da célula restrita aos acidentes que envolvem uma categoria
    de veículo (`moto`, `carro`, `caminhao`, `onibus`), com o nível
    recalculado entre as células para aquela categoria (ver `ml.veiculos`)."""

    __tablename__ = "risco_celulas_veiculo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    celula: Mapped[str] = mapped_column(String(30), index=True)
    veiculo: Mapped[str] = mapped_column(String(20), index=True)
    fracao: Mapped[float] = mapped_column(Float)
    acidentes_esperados: Mapped[float] = mapped_column(Float)
    nivel_risco: Mapped[str] = mapped_column(String(10))


class RiscoVia(Base):
    """Previsão de acidentes da via nos próximos 12 meses: soma das fatias
    dela em cada célula onde aparece (ver `ml.ocorrencia.gerar_ranking`)."""

    __tablename__ = "risco_vias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    via: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    acidentes_esperados: Mapped[float] = mapped_column(Float)
    acidentes_historico: Mapped[float] = mapped_column(Float)
    nivel_risco: Mapped[str] = mapped_column(String(10))
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)


class RiscoPerfilHorario(Base):
    """Fração dos acidentes de um escopo (uma via ou `__cidade__`) em cada
    dia da semana (0 = segunda) x hora. Soma 1 por escopo."""

    __tablename__ = "risco_perfil_horario"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    escopo: Mapped[str] = mapped_column(String(255), index=True)
    dia_semana: Mapped[int] = mapped_column(Integer)
    hora: Mapped[int] = mapped_column(Integer)
    fracao: Mapped[float] = mapped_column(Float)


class RiscoPontoCritico(Base):
    """Aglomerado de acidentes com óbito (DBSCAN, ver `ml.pontos_criticos`)."""

    __tablename__ = "risco_pontos_criticos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    raio_m: Mapped[float] = mapped_column(Float)
    n_acidentes_fatais: Mapped[int] = mapped_column(Integer)
    n_obitos: Mapped[int] = mapped_column(Integer)
    rua_principal: Mapped[str | None] = mapped_column(String(255))
    primeiro: Mapped[dt.date] = mapped_column(Date)
    ultimo: Mapped[dt.date] = mapped_column(Date)


class RiscoPrevisaoMensal(Base):
    """Total mensal da cidade: `real` no histórico (nulo em mês sem dados na
    fonte) e `previsto` com intervalo de 95% nos meses futuros."""

    __tablename__ = "risco_previsao_mensal"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mes: Mapped[str] = mapped_column(String(7), unique=True)
    real: Mapped[float | None] = mapped_column(Float)
    previsto: Mapped[float] = mapped_column(Float)
    limite_inferior: Mapped[float | None] = mapped_column(Float)
    limite_superior: Mapped[float | None] = mapped_column(Float)
    futuro: Mapped[bool] = mapped_column(Boolean, default=False)


class MlExecucao(Base):
    """Uma publicação do treino: modelo escolhido, métricas do backtest e
    resumo da limpeza. A mais recente é a que está nas tabelas acima."""

    __tablename__ = "ml_execucoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gerado_em: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)
    fonte: Mapped[str] = mapped_column(String(255))
    modelo_ocorrencia: Mapped[str] = mapped_column(String(30))
    janela_previsao: Mapped[str] = mapped_column(String(30))
    metricas: Mapped[dict] = mapped_column(JSON)
    resumo_limpeza: Mapped[dict] = mapped_column(JSON)
