from __future__ import annotations

from datetime import datetime, date
from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import select, or_

from app.config import settings
from app.models import CaseRecord, CaseExtraction
from app.jobs.poll_cases import ingest_recent_cases
from app.services.extractor import extract_case
from app.services.scoring import recompute_judge_scores, recompute_judge_phrase_scores
from app.services.text_enricher import batch_enrich_text


def _apply_extraction_to_case(db: Session, case: CaseRecord) -> tuple[CaseExtraction | None, str]:
    """
    Returns (extraction_or_none, status)
    status in {"created", "updated", "skipped_no_text", "skipped_no_full_text", "error"}
    """
    text = (case.opinion_text or "").strip()
    snippet = (case.text_excerpt or "").strip()

    source_text = text if text else snippet
    if not source_text:
        return None, "skipped_no_text"

    if settings.require_opinion_text_for_auto_extract and not text:
        return None, "skipped_no_full_text"

    try:
        result = extract_case(source_text)

        ext = db.query(CaseExtraction).filter_by(case_id=case.id).one_or_none()
        is_new = ext is None
        if is_new:
            ext = CaseExtraction(case_id=case.id)
            db.add(ext)

        ext.petitioner_facts = result.petitioner_facts
        ext.petition_facts = result.petition_facts
        ext.respondent_position = result.respondent_position
        ext.reasoning_basis = result.reasoning_basis
        ext.precedent_citations = result.precedent_citations
        ext.holdings = result.holdings
        ext.phrase_signals = result.phrase_signals
        ext.evidence_spans = result.evidence_spans
        ext.is_border_or_near_border_detention = result.flags.get("is_border_or_near_border_detention")
        ext.is_interior_detention_focus = result.flags.get("is_interior_detention_focus")
        ext.confidence = result.confidence

        # Auto review gating
        if (result.confidence or 0.0) < settings.auto_review_confidence_threshold:
            ext.review_status = "needs_review"
        else:
            # If location flags conflict/ambiguous, push to review
            border_flag = ext.is_border_or_near_border_detention
            interior_flag = ext.is_interior_detention_focus
            if border_flag is True and interior_flag is True:
                ext.review_status = "needs_review"
            else:
                ext.review_status = "auto"

        case.updated_at = datetime.utcnow()
        db.flush()

        return ext, ("created" if is_new else "updated")
    except Exception:
        return None, "error"


def batch_extract_unprocessed_cases(db: Session, limit: int | None = None) -> dict[str, Any]:
    """
    Auto-extracts cases that do not yet have an extraction.
    """
    if limit is None:
        limit = settings.extraction_batch_limit

    stmt = (
        select(CaseRecord)
        .outerjoin(CaseExtraction, CaseExtraction.case_id == CaseRecord.id)
        .where(CaseExtraction.id.is_(None))
        .where(
            or_(
                CaseRecord.opinion_text.is_not(None),
                CaseRecord.text_excerpt.is_not(None),
            )
        )
        .order_by(CaseRecord.decision_date.desc().nullslast(), CaseRecord.id.desc())
        .limit(limit)
    )
    cases = db.execute(stmt).scalars().all()

    stats = {
        "selected": len(cases),
        "created": 0,
        "updated": 0,
        "skipped_no_text": 0,
        "skipped_no_full_text": 0,
        "error": 0,
        "case_ids": [],
    }

    for case in cases:
        _, status = _apply_extraction_to_case(db, case)
        stats[status] = stats.get(status, 0) + 1
        if status in {"created", "updated"}:
            stats["case_ids"].append(case.id)

    db.commit()
    return stats


def reextract_cases_for_review(db: Session, limit: int = 25) -> dict[str, Any]:
    """
    Re-run extraction for items marked needs_review after rules/lexicons improve.
    """
    stmt = (
        select(CaseRecord, CaseExtraction)
        .join(CaseExtraction, CaseExtraction.case_id == CaseRecord.id)
        .where(CaseExtraction.review_status == "needs_review")
        .order_by(CaseRecord.decision_date.desc().nullslast(), CaseRecord.id.desc())
        .limit(limit)
    )
    rows = db.execute(stmt).all()

    stats = {"selected": len(rows), "updated": 0, "skipped_no_text": 0, "skipped_no_full_text": 0, "error": 0}
    for case, _ in rows:
        _, status = _apply_extraction_to_case(db, case)
        stats[status] = stats.get(status, 0) + 1

    db.commit()
    return stats


def run_pipeline_once(db: Session) -> dict[str, Any]:
    """
    End-to-end agent loop:
    1) Ingest recent cases
    2) Enrich text for cases missing opinion text (optional)
    3) Extract unprocessed cases
    4) Recompute judge scores
    """
    started = datetime.utcnow()

    ingest_stats = ingest_recent_cases(db)

    enrich_stats = None
    if settings.enable_text_enrichment_in_pipeline:
        enrich_stats = batch_enrich_text(
            db,
            limit=settings.enrichment_batch_limit,
            overwrite=False,
            timeout=settings.enrichment_timeout_seconds,
        )

    extract_stats = batch_extract_unprocessed_cases(db, limit=settings.extraction_batch_limit)
    score_count = recompute_judge_scores(db, as_of=date.today())
    phrase_score_count = recompute_judge_phrase_scores(db, as_of=date.today())

    finished = datetime.utcnow()

    return {
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "ingest": ingest_stats,
        "enrich_text": enrich_stats,
        "extract": extract_stats,
        "scores": {
            "created_snapshots": score_count,
            "created_phrase_snapshots": phrase_score_count,
        },
    }