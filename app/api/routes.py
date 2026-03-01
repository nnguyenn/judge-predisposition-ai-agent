from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_db
from app.models import CaseRecord, CaseExtraction, JudgeIssueScore
from app.schemas import CaseOut, ExtractionOut, JudgeScoreOut
from app.jobs.poll_cases import ingest_recent_cases
from app.jobs.pipeline import (
    batch_extract_unprocessed_cases,
    reextract_cases_for_review,
    run_pipeline_once,
)
from app.services.extractor import extract_case
from app.services.scoring import recompute_judge_scores

router = APIRouter()


@router.get("/health")
def health():
    return {"ok": True}


@router.post("/ingest/run-once")
def run_ingest(db: Session = Depends(get_db)):
    return ingest_recent_cases(db)


@router.post("/pipeline/run-once")
def pipeline_run_once(db: Session = Depends(get_db)):
    return run_pipeline_once(db)


@router.post("/extract/batch")
def extract_batch(
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return batch_extract_unprocessed_cases(db, limit=limit)


@router.post("/extract/review/retry")
def retry_review_extractions(
    limit: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
):
    return reextract_cases_for_review(db, limit=limit)


@router.get("/review/queue")
def review_queue(
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(CaseRecord, CaseExtraction)
        .join(CaseExtraction, CaseExtraction.case_id == CaseRecord.id)
        .filter(CaseExtraction.review_status == "needs_review")
        .order_by(CaseRecord.decision_date.desc().nullslast(), CaseRecord.id.desc())
        .limit(limit)
        .all()
    )

    out = []
    for case, ext in rows:
        out.append({
            "case_id": case.id,
            "case_caption": case.case_caption,
            "court": case.court,
            "judge_name": case.judge_name,
            "decision_date": case.decision_date.isoformat() if case.decision_date else None,
            "confidence": ext.confidence,
            "review_status": ext.review_status,
            "holdings": ext.holdings,
            "reasoning_basis": ext.reasoning_basis,
            "location_flags": {
                "is_border_or_near_border_detention": ext.is_border_or_near_border_detention,
                "is_interior_detention_focus": ext.is_interior_detention_focus,
            },
            "evidence_spans": ext.evidence_spans,
            "opinion_url": case.opinion_url,
        })
    return out


@router.post("/review/{case_id}/mark")
def mark_review_status(
    case_id: int,
    status: str = Query(..., pattern="^(reviewed|rejected|auto|needs_review)$"),
    db: Session = Depends(get_db),
):
    ext = db.query(CaseExtraction).filter_by(case_id=case_id).one_or_none()
    if not ext:
        raise HTTPException(status_code=404, detail="Extraction not found for case")

    ext.review_status = status
    db.commit()
    db.refresh(ext)
    return {"case_id": case_id, "review_status": ext.review_status}


@router.get("/cases", response_model=list[CaseOut])
def list_cases(
    judge_name: str | None = None,
    limit: int = Query(default=50, le=200),
    db: Session = Depends(get_db),
):
    stmt = select(CaseRecord).order_by(CaseRecord.decision_date.desc().nullslast(), CaseRecord.id.desc()).limit(limit)
    if judge_name:
        stmt = stmt.where(CaseRecord.judge_name.ilike(f"%{judge_name}%"))
    return db.execute(stmt).scalars().all()


@router.get("/cases/{case_id}")
def get_case_detail(case_id: int, db: Session = Depends(get_db)):
    case = db.get(CaseRecord, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    ext = db.query(CaseExtraction).filter_by(case_id=case_id).one_or_none()

    return {
        "case": {
            "id": case.id,
            "case_caption": case.case_caption,
            "court": case.court,
            "district_court": case.district_court,
            "judge_name": case.judge_name,
            "judge_role": case.judge_role,
            "decision_date": case.decision_date.isoformat() if case.decision_date else None,
            "opinion_url": case.opinion_url,
            "docket_url": case.docket_url,
            "text_excerpt": case.text_excerpt,
            "opinion_text_preview": (case.opinion_text[:2000] if case.opinion_text else None),
        },
        "extraction": None if not ext else {
            "confidence": ext.confidence,
            "review_status": ext.review_status,
            "holdings": ext.holdings,
            "reasoning_basis": ext.reasoning_basis,
            "precedent_citations": ext.precedent_citations,
            "flags": {
                "is_border_or_near_border_detention": ext.is_border_or_near_border_detention,
                "is_interior_detention_focus": ext.is_interior_detention_focus,
            },
            "evidence_spans": ext.evidence_spans,
        }
    }


@router.post("/cases/{case_id}/extract", response_model=ExtractionOut)
def extract_case_endpoint(case_id: int, db: Session = Depends(get_db)):
    case = db.get(CaseRecord, case_id)
    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    source_text = case.opinion_text or case.text_excerpt or ""
    if not source_text.strip():
        raise HTTPException(status_code=400, detail="No opinion text/snippet available to extract from")

    result = extract_case(source_text)

    ext = db.query(CaseExtraction).filter_by(case_id=case.id).one_or_none()
    if not ext:
        ext = CaseExtraction(case_id=case.id)
        db.add(ext)

    ext.petitioner_facts = result.petitioner_facts
    ext.petition_facts = result.petition_facts
    ext.respondent_position = result.respondent_position
    ext.reasoning_basis = result.reasoning_basis
    ext.precedent_citations = result.precedent_citations
    ext.holdings = result.holdings
    ext.evidence_spans = result.evidence_spans
    ext.is_border_or_near_border_detention = result.flags.get("is_border_or_near_border_detention")
    ext.is_interior_detention_focus = result.flags.get("is_interior_detention_focus")
    ext.confidence = result.confidence
    ext.review_status = "auto"

    db.commit()
    db.refresh(ext)
    return ext


@router.post("/scores/recompute")
def recompute_scores(db: Session = Depends(get_db)):
    created = recompute_judge_scores(db)
    return {"created_snapshots": created}


@router.get("/judges/{judge_name}/scores", response_model=list[JudgeScoreOut])
def get_judge_scores(judge_name: str, db: Session = Depends(get_db)):
    # FIXED: wildcard pattern so partial names work
    rows = (
        db.query(JudgeIssueScore)
        .filter(JudgeIssueScore.judge_name.ilike(f"%{judge_name}%"))
        .order_by(JudgeIssueScore.as_of_date.desc(), JudgeIssueScore.segment.asc())
        .all()
    )
    return rows