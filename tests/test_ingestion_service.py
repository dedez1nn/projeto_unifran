from app.db.session import Base, SessionLocal, engine
from app.services.ingestion_service import ingest_csv_bytes


def setup_module() -> None:
    Base.metadata.create_all(bind=engine)


def test_linha_duplicada_no_mesmo_arquivo_vira_update_sem_quebrar():
    db = SessionLocal()
    try:
        csv = b"id_sinistro;municipio\n1;RIBEIRAO PRETO\n1;RIBEIRAO PRETO\n"
        summary = ingest_csv_bytes(db, csv, "duplicata_mesmo_arquivo.csv")
    finally:
        db.close()

    assert summary.total_rows == 2
    assert summary.inserted == 1
    assert summary.updated == 1


def test_id_coincidente_entre_arquivos_diferentes_nao_colide():
    db = SessionLocal()
    try:
        csv = b"id_sinistro;municipio\n42;RIBEIRAO PRETO\n"
        resumo_a = ingest_csv_bytes(db, csv, "fonte_a.csv")
        resumo_b = ingest_csv_bytes(db, csv, "fonte_b.csv")
    finally:
        db.close()

    # mesmo id_sinistro (42), arquivos diferentes -> dois registros distintos,
    # nenhum tratado como update do outro
    assert resumo_a.inserted == 1
    assert resumo_b.inserted == 1
    assert resumo_b.updated == 0


def test_reingestao_do_mesmo_arquivo_e_idempotente():
    db = SessionLocal()
    try:
        csv = b"id_sinistro;municipio\n7;RIBEIRAO PRETO\n"
        primeira = ingest_csv_bytes(db, csv, "reingestao.csv")
        segunda = ingest_csv_bytes(db, csv, "reingestao.csv")
    finally:
        db.close()

    assert primeira.inserted == 1
    assert primeira.updated == 0
    assert segunda.inserted == 0
    assert segunda.updated == 1
