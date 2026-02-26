from __future__ import annotations

from datetime import datetime, date
from sqlalchemy import (
    String, Integer, DateTime, Date, Boolean, Text, ForeignKey, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class IngestionRun(Base):
    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), index=True)
    query: Mapped[str] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    inserted_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class CaseRecord(Base):
    __tablename__ = "cases"
    __table_args__ = (
        UniqueConstraint("source", "source_case_id", name="uq_case_source_id"),
        Index("ix_cases_judge_name", "judge_name"),
        Index("ix_cases_decision_date", "decision_date"),
        Index("ix_cases_court", "court"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Retrieval identity
    source: Mapped[str] = mapped_column(String(64), default="courtlistener")
    source_case_id: Mapped[str] = mapped_column(String(255))
    source_cluster_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Core metadata
    case_caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    court: Mapped[str | None] = mapped_column(String(255), nullable=True)
    district_court: Mapped[str | None] = mapped_column(String(255), nullable=True)
    judge_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    judge_role: Mapped[str | None] = mapped_column(String(64), nullable=True)  # district/magistrate/unknown
    decision_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Opinion text / urls
    opinion_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    docket_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    text_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)  # retrieval snippet
    opinion_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Tracking
    retrieval_payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    extraction: Mapped["CaseExtraction | None"] = relationship(
        back_populates="case", uselist=False, cascade="all, delete-orphan"
    )


class CaseExtraction(Base):
    __tablename__ = "case_extractions"
    __table_args__ = (
        UniqueConstraint("case_id", name="uq_case_extraction_case_id"),
        Index("ix_extractions_review_status", "review_status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"))

    # Memo sections stored as JSON for MVP
    petitioner_facts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    petition_facts: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    respondent_position: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Reasoning basis categories from memo
    reasoning_basis: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    precedent_citations: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Holdings (memo priority)
    holdings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Important flags
    is_border_or_near_border_detention: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    is_interior_detention_focus: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Evidence spans + confidence
    evidence_spans: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    confidence: Mapped[float | None] = mapped_column(nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="auto")  # auto/reviewed/rejected

    extracted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    case: Mapped["CaseRecord"] = relationship(back_populates="extraction")


class JudgeIssueScore(Base):
    __tablename__ = "judge_issue_scores"
    __table_args__ = (
        UniqueConstraint("judge_name", "as_of_date", "segment", name="uq_judge_score_snapshot"),
        Index("ix_judge_scores_judge_name", "judge_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    judge_name: Mapped[str] = mapped_column(String(255))
    as_of_date: Mapped[date] = mapped_column(Date)

    # segment examples: "all", "interior_detention", "near_border"
    segment: Mapped[str] = mapped_column(String(64), default="all")

    n_cases: Mapped[int] = mapped_column(Integer, default=0)

    # Smoothed rates (descriptive patterns, not “bias”)
    rate_1226: Mapped[float | None] = mapped_column(nullable=True)
    rate_bond_eligible: Mapped[float | None] = mapped_column(nullable=True)
    rate_habeas_granted: Mapped[float | None] = mapped_column(nullable=True)

    # confidence intervals / metadata
    ci_low: Mapped[float | None] = mapped_column(nullable=True)
    ci_high: Mapped[float | None] = mapped_column(nullable=True)
    model_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)