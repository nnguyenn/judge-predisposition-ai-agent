from __future__ import annotations

from datetime import datetime
from dateutil import parser as dtparser
from sqlalchemy.orm import Session

from app.models import IngestionRun, CaseRecord
from app.services.retrieval_client import RetrievalClient
from app.config import settings


def _safe_date(raw):
    if not raw:
        return None
    try:
        return dtparser.parse(raw).date()
    except Exception:
        return None


def _pick(row: dict, *keys):
    for k in keys:
        if k in row and row[k] not in (None, ""):
            return row[k]
    return None


def ingest_recent_cases(db: Session) -> dict:
    client = RetrievalClient()
    run = IngestionRun(source="retrieval_api", query=settings.poll_query)
    db.add(run)
    db.commit()
    db.refresh(run)

    fetched = 0
    inserted = 0

    try:
        results = client.search_recent_cases(
            query=settings.poll_query,
            lookback_days=settings.poll_lookback_days,
            page_size=settings.poll_max_results,
        )
        fetched = len(results)

        for row in results:
            source_case_id = str(_pick(row, "id", "pk", "resource_uri", "absolute_url", "cluster_id"))
            if not source_case_id:
                continue

            existing = db.query(CaseRecord).filter_by(source="courtlistener", source_case_id=source_case_id).one_or_none()
            if existing:
                # lightweight update
                existing.updated_at = datetime.utcnow()
                continue

            case = CaseRecord(
                source="courtlistener",
                source_case_id=source_case_id,
                source_cluster_id=str(_pick(row, "cluster_id", "cluster")) if _pick(row, "cluster_id", "cluster") else None,
                case_caption=_pick(row, "caseName", "case_name", "caseNameFull", "caption"),
                court=_pick(row, "court", "court_id"),
                district_court=_pick(row, "court", "court_id"),
                judge_name=_pick(row, "judge", "judge_name", "assigned_to_str"),
                judge_role=None,
                decision_date=_safe_date(_pick(row, "dateFiled", "date_filed", "date")),
                opinion_url=_pick(row, "absolute_url", "download_url", "url"),
                docket_url=_pick(row, "docket_absolute_url", "docket_url"),
                text_excerpt=_pick(row, "snippet", "text"),
                opinion_text=_pick(row, "plain_text", "text"),  # many APIs only return snippet here
                retrieval_payload=row,
            )
            db.add(case)
            inserted += 1

        run.fetched_count = fetched
        run.inserted_count = inserted
        run.finished_at = datetime.utcnow()
        db.commit()

        return {"fetched": fetched, "inserted": inserted, "run_id": run.id}

    except Exception as e:
        run.finished_at = datetime.utcnow()
        run.notes = {"error": str(e)}
        db.commit()
        raise