from datetime import date
from pydantic import BaseModel
from typing import Any


class CaseOut(BaseModel):
    id: int
    case_caption: str | None
    court: str | None
    judge_name: str | None
    decision_date: date | None
    opinion_url: str | None

    class Config:
        from_attributes = True


class ExtractionOut(BaseModel):
    case_id: int
    reasoning_basis: dict[str, Any] | None
    holdings: dict[str, Any] | None
    phrase_signals: list[dict[str, Any]] | None
    is_border_or_near_border_detention: bool | None
    is_interior_detention_focus: bool | None
    confidence: float | None

    class Config:
        from_attributes = True

    class Config:
        from_attributes = True


class JudgeScoreOut(BaseModel):
    judge_name: str
    as_of_date: date
    segment: str
    n_cases: int
    rate_1226: float | None
    rate_bond_eligible: float | None
    rate_habeas_granted: float | None
    ci_low: float | None
    ci_high: float | None

    class Config:
        from_attributes = True

class JudgePhraseScoreOut(BaseModel):
    judge_name: str
    as_of_date: date
    segment: str
    phrase_key: str
    phrase_label: str
    phrase_category: str
    n_cases: int
    favorable_count: int
    unfavorable_count: int
    other_count: int
    favorable_rate: float | None
    unfavorable_rate: float | None
    direction: str
    sample_case_ids: list[int] | None
    sample_evidence: list[dict[str, Any]] | None

    class Config:
        from_attributes = True