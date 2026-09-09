from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, health, ingestion, mapa, sinistros
from app.core.config import settings
from app.db.models import Sinistro, User  # noqa: F401 - garante registro dos models no Base
from app.db.session import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="API de Sinistros de Trânsito - Ribeirão Preto",
    description=(
        "Ingestão e consulta de dados de sinistros de trânsito, escopo "
        "Ribeirão Preto-SP, para consumo do time de análise/predição de "
        "zonas de risco."
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(health.router)
app.include_router(ingestion.router)
app.include_router(mapa.router)
app.include_router(sinistros.router)
