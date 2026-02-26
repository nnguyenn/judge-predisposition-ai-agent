from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import get_db
from app.models import CaseRecord, CaseExtraction, JudgeIssueScore
from app.schemas import CaseOut, ExtractionOut, JudgeScoreOut
from app.jobs.poll_cases import ingest_recent_cases
from app.services.extractor import extract_case
from app.services.scoring import recompute_judge_scores

router = APIRouter()


@router.get("/health")
def health():
    return {"ok": True}


@router.post("/ingest/run-once")
def run_ingest(db: Session = Depends(get_db)):
    return ingest_recent_cases(db)


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

    db.commit()
    db.refresh(ext)
    return ext


@router.post("/scores/recompute")
def recompute_scores(db: Session = Depends(get_db)):
    created = recompute_judge_scores(db)
    return {"created_snapshots": created}


@router.get("/judges/{judge_name}/scores", response_model=list[JudgeScoreOut])
def get_judge_scores(judge_name: str, db: Session = Depends(get_db)):
    rows = db.query(JudgeIssueScore).filter(JudgeIssueScore.judge_name.ilike(judge_name)).order_by(
        JudgeIssueScore.as_of_date.desc(), JudgeIssueScore.segment.asc()
    ).all()
    return rows