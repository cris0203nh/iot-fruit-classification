"""AG-040 / AGROP-48 — Informe exportable y auditoría por lote (solo lectura).

El CSV contiene una fila por clave (lote, pieza), nunca por evaluación/imagen.
El SHA-256 corresponde exclusivamente a los bytes UTF-8 del CSV canónico.
"""
from __future__ import annotations

import csv
import hashlib
import io
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_authenticated
from ..models import Evaluation, Image, Review, User
from ..vision_assessment_models import VisionAssessment
from ..decision_models import ReviewDecisionEvidence
from .piece_history import _group_lot, _lot

router = APIRouter(tags=["reporte-historial-por-lote"])
VERSION = "AG040-02-v1"
HEADERS = [
    "lote", "pieza", "origen_identidad", "piezas_unicas", "intentos",
    "fotografias", "evaluaciones_automaticas", "eventos_revision",
    "ids_intentos", "ids_fotografias", "ids_evaluaciones_automaticas",
    "ids_revisiones", "versiones_modelo", "versiones_reglas", "observaciones",
]


def _id(prefix: str, value: int) -> str:
    return f"{prefix}-{value:06d}"


def _csv_value(value: object) -> str:
    """Evita que códigos de pieza ingresados por operadores ejecuten fórmulas en Excel."""
    text = str(value if value is not None else "")
    if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")):
        return "'" + text
    return text


def _export_csv(rows: list[dict]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow(HEADERS)
    for row in rows:
        writer.writerow([_csv_value(value) for value in (
            row["lotCode"], row["pieceCode"], row["identitySource"], 1,
            row["attemptCount"], row["captureCount"], row["automaticAssessmentCount"],
            row["reviewEventCount"], " | ".join(row["attemptIds"]),
            " | ".join(row["captureIds"]), " | ".join(row["assessmentIds"]),
            " | ".join(row["reviewIds"]), " | ".join(row["modelVersions"]),
            " | ".join(row["rulesVersions"]), " | ".join(row["qualityNotes"]),
        )])
    return buf.getvalue()


def _compile_report(db: Session, lot) -> dict:
    summaries = _group_lot(db, lot)  # También verifica FKs inconsistentes (HTTP 409).
    attempts = db.scalars(select(Evaluation).where(Evaluation.lot_id == lot.id).order_by(Evaluation.id)).all()
    ids = [a.id for a in attempts]
    images = db.scalars(select(Image).where(Image.evaluation_id.in_(ids)).order_by(Image.id)).all() if ids else []
    assessments = db.scalars(select(VisionAssessment).where(VisionAssessment.evaluation_id.in_(ids)).order_by(VisionAssessment.id)).all() if ids else []
    reviews = db.scalars(select(Review).where(Review.evaluation_id.in_(ids)).order_by(Review.id)).all() if ids else []
    review_ids = [r.id for r in reviews]
    metadata = db.scalars(select(ReviewDecisionEvidence).where(ReviewDecisionEvidence.review_id.in_(review_ids))).all() if review_ids else []

    ev_by_code: dict[str, list] = defaultdict(list)
    image_by_ev: dict[int, list] = defaultdict(list)
    assessment_by_ev: dict[int, list] = defaultdict(list)
    review_by_ev: dict[int, list] = defaultdict(list)
    meta_by_review = {m.review_id: m for m in metadata}
    for e in attempts:
        ev_by_code[e.piece_id].append(e)
    for i in images:
        image_by_ev[i.evaluation_id].append(i)
    for a in assessments:
        assessment_by_ev[a.evaluation_id].append(a)
    for r in reviews:
        review_by_ev[r.evaluation_id].append(r)

    issues: list[dict] = []
    def issue(severity: str, code: str, piece: str, message: str) -> None:
        issues.append({"severity": severity, "code": code, "pieceCode": piece, "message": message})

    rows = []
    for summary in summaries:
        code = summary["pieceCode"]
        evs = ev_by_code[code]
        photos = [p for e in evs for p in image_by_ev[e.id]]
        auto = [a for e in evs for a in assessment_by_ev[e.id]]
        human = [r for e in evs for r in review_by_ev[e.id]]
        images_per_attempt = {e.id: {p.id for p in image_by_ev[e.id]} for e in evs}
        hashes: dict[int, set[str]] = defaultdict(set)
        notes = []
        if summary["identitySource"] == "legacy_inferred":
            issue("warning", "IDENTIDAD_HISTORICA", code, "Pieza inferida por codigo; no hay registro normalizado de pieza fisica")
            notes.append("Identidad historica inferida")
        for a in auto:
            if a.image_id not in images_per_attempt[a.evaluation_id]:
                issue("error", "FOTO_SNAPSHOT_AJENA", code, f"Snapshot {a.id} referencia una foto ajena al intento")
            hashes[a.image_id].add(a.image_sha256)
        for r in human:
            meta = meta_by_review.get(r.id)
            if meta:
                if meta.evaluation_id != r.evaluation_id or meta.image_id not in images_per_attempt[r.evaluation_id]:
                    issue("error", "FOTO_REVISION_AJENA", code, f"Revision {r.id} referencia otra evaluacion o fotografia")
                hashes[meta.image_id].add(meta.image_sha256)
        for photo in photos:
            known = hashes.get(photo.id, set())
            if len(known) > 1:
                issue("error", "HASH_DIVERGENTE", code, f"SHA256 contradictorio para {_id('I', photo.id)}")
                notes.append(f"Hash divergente en {_id('I', photo.id)}")
            elif not known:
                issue("warning", "HASH_NO_ACREDITADO", code, f"No existe SHA256 referenciado para {_id('I', photo.id)}")
                notes.append(f"Hash no acreditado en {_id('I', photo.id)}")
        row = {
            "lotCode": lot.code,
            "pieceCode": code,
            "identitySource": summary["identitySource"],
            "attemptCount": len(evs),
            "captureCount": len(photos),
            "automaticAssessmentCount": len(auto),
            "reviewEventCount": len(human),
            "attemptIds": [_id("E", e.id) for e in evs],
            "captureIds": [_id("I", p.id) for p in photos],
            "assessmentIds": [str(a.id) for a in auto],
            "reviewIds": [_id("R", r.id) for r in human],
            "modelVersions": sorted({a.model_version for a in auto if a.model_version}),
            "rulesVersions": sorted({a.rules_version for a in auto if a.rules_version}),
            "qualityNotes": notes,
        }
        for k in ("attemptCount", "captureCount", "automaticAssessmentCount", "reviewEventCount"):
            if row[k] != summary[k]:
                issue("error", "CONTEO_DIVERGENTE", code, f"Contador {k} no coincide con expediente")
        rows.append(row)

    totals = {
        "pieceCount": len(rows),
        "attemptCount": len(attempts),
        "captureCount": len(images),
        "automaticAssessmentCount": len(assessments),
        "reviewEventCount": len(reviews),
    }
    observed = {"attemptCount": 0, "captureCount": 0, "automaticAssessmentCount": 0, "reviewEventCount": 0}
    for row in rows:
        for key in observed:
            observed[key] += row[key]
    for key, count in observed.items():
        if count != totals[key]:
            issue("error", "TOTAL_DIVERGENTE", "", f"Total {key} ({count}) no concuerda con registros SQL ({totals[key]})")
    if len({row["pieceCode"] for row in rows}) != len(rows):
        issue("error", "PIEZA_REPETIDA", "", "Se detectaron identidades repetidas dentro del lote")

    status = "inconsistent" if any(x["severity"] == "error" for x in issues) else ("warning" if issues else "ok")
    csv_text = _export_csv(rows)
    return {
        "reportVersion": VERSION,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "lotCode": lot.code,
        "product": lot.product,
        "counts": totals,
        "integrity": {"status": status, "issues": issues},
        "rows": rows,
        "csv": csv_text,
        "csvSha256": hashlib.sha256(csv_text.encode("utf-8")).hexdigest(),
        "csvEncoding": "UTF-8",
    }


@router.get("/api/piece-history/report")
def get_lot_piece_report(
    response: Response,
    lot: str = Query(min_length=1, max_length=32),
    db: Session = Depends(get_db),
    _user: User = Depends(require_authenticated),
):
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return _compile_report(db, _lot(db, lot))
