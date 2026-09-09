import csv
import datetime as dt
import io
import re
import unicodedata
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Sinistro
from app.schemas.sinistro import IngestionSummary
from app.services.adapters import LinhaInvalidaError, parse_row_generico

AVISOS_MAX = 50  # não deixa o resumo virar um arquivo de log inteiro


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=";,\t").delimiter
    except csv.Error:
        return ";"


def _decode(file_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("latin-1", errors="replace")


def _source_name_from_filename(source_filename: str) -> str:
    """Deriva `source_name` do nome do arquivo, não de uma constante fixa —
    cada arquivo é o seu próprio namespace de `source_row_id`. Isso evita que
    um id igual por coincidência entre dois arquivos de fontes diferentes
    (ex: id_sinistro do CSV oficial batendo com num_acidente de outro CSV)
    seja tratado como "a mesma linha" e sobrescreva dados de um sinistro com
    os de outro completamente diferente.
    """
    stem = Path(source_filename).stem
    normalized = unicodedata.normalize("NFKD", stem).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", normalized).strip("_").lower()
    return (slug or "arquivo")[:50]


def ingest_csv_bytes(
    db: Session, file_bytes: bytes, source_filename: str
) -> IngestionSummary:
    """Ingesta um CSV de sinistros de formato arbitrário (ver
    `services/adapters.py`), restrito ao município configurado quando o
    arquivo declara essa coluna (padrão: Ribeirão Preto). Reingestões fazem
    upsert por `(source_name, source_row_id)`, então rodar o mesmo arquivo de
    novo é seguro (idempotente) mesmo sem um `id_sinistro` reconhecível.
    """
    text = _decode(file_bytes)
    delimiter = _sniff_delimiter(text[:4096])
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)

    source_name = _source_name_from_filename(source_filename)

    # Uma consulta só (não uma por linha — evita N+1 queries em arquivos
    # grandes) para saber o que já existe dessa fonte; o dict também serve
    # de "memória" das linhas já processadas *neste* arquivo, então uma
    # linha duplicada dentro do próprio CSV vira update em vez de dar
    # conflito de chave única no commit (a sessão não vê seus próprios
    # `add()` ainda não commitados sem isso).
    existentes: dict[str, Sinistro] = {
        s.source_row_id: s
        for s in db.query(Sinistro).filter(Sinistro.source_name == source_name)
    }

    total = inserted = updated = skipped_other_municipio = skipped_invalid = 0
    avisos: list[str] = []
    avisos_gerados = 0
    colunas_nao_mapeadas: set[str] = set()
    municipio_reconhecido_no_arquivo = False

    def registrar_aviso(msg: str) -> None:
        nonlocal avisos_gerados
        avisos_gerados += 1
        if len(avisos) < AVISOS_MAX:
            avisos.append(msg)

    for row_num, raw_row in enumerate(reader, start=2):  # linha 1 é o cabeçalho
        total += 1
        try:
            parsed = parse_row_generico(raw_row)
        except LinhaInvalidaError as exc:
            skipped_invalid += 1
            registrar_aviso(f"linha {row_num}: {exc}")
            continue

        colunas_nao_mapeadas.update(parsed.unmapped_columns)
        for aviso in parsed.warnings:
            registrar_aviso(f"linha {row_num}: {aviso}")

        if parsed.municipio_informado:
            municipio_reconhecido_no_arquivo = True
            municipio = (parsed.fields.get("municipio") or "").strip().upper()
            if municipio != settings.municipio_alvo:
                skipped_other_municipio += 1
                continue

        data = dict(parsed.fields)
        data["source_name"] = source_name
        data["source_row_id"] = parsed.source_row_id
        data["source_file"] = source_filename
        data["ingested_at"] = dt.datetime.now(dt.timezone.utc)
        data["raw_data"] = {str(k): v for k, v in raw_row.items() if k is not None}

        existing = existentes.get(parsed.source_row_id)
        if existing is not None:
            for key, value in data.items():
                setattr(existing, key, value)
            updated += 1
        else:
            novo = Sinistro(**data)
            db.add(novo)
            existentes[parsed.source_row_id] = novo
            inserted += 1

    db.commit()

    if total and not municipio_reconhecido_no_arquivo:
        avisos.insert(
            0,
            "arquivo sem coluna de município reconhecida — filtro de "
            f"MUNICIPIO_ALVO ('{settings.municipio_alvo}') não foi aplicado, "
            "todas as linhas válidas foram aceitas",
        )

    if avisos_gerados > len(avisos):
        avisos.append(
            f"... e mais {avisos_gerados - len(avisos)} aviso(s) omitido(s) "
            f"(limite de exibição: {AVISOS_MAX})"
        )

    return IngestionSummary(
        source_file=source_filename,
        total_rows=total,
        inserted=inserted,
        updated=updated,
        skipped_other_municipio=skipped_other_municipio,
        skipped_invalid=skipped_invalid,
        colunas_nao_mapeadas=sorted(colunas_nao_mapeadas),
        avisos=avisos,
    )
