from __future__ import annotations

from collections import defaultdict
from datetime import date
from math import sqrt
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.models import CaseRecord, CaseExtraction, JudgeIssueScore, JudgePhraseScore


FAVORABLE_RELIEF_VALUES = {
    "granted",
    "granted_in_part",
    "granted_in_part_and_denied_in_part",
}
UNFAVORABLE_RELIEF_VALUES = {
    "denied",
    "denied_in_part",
}


def _wilson_interval(successes: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    if n == 0:
        return None, None
    p = successes / n
    denom = 1 + z**2 / n
    center = (p + z**2 / (2 * n)) / denom
    margin = z * sqrt((p * (1 - p) + z**2 / (4 * n)) / n) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def recompute_judge_scores(db: Session, as_of: date | None = None) -> int:
    if as_of is None:
        as_of = date.today()

    rows = db.execute(
        select(CaseRecord, CaseExtraction)
        .join(CaseExtraction, CaseExtraction.case_id == CaseRecord.id)
        .where(CaseRecord.judge_name.is_not(None))
        .where(CaseExtraction.review_status.in_(["auto", "reviewed"]))
    ).all()

    global_n = 0
    g_1226 = g_bond = g_habeas = 0

    parsed = []
    for case, ext in rows:
        h = ext.holdings or {}
        parsed.append((case, ext, h))

        global_n += 1
        if h.get("applicable_provision") == "1226":
            g_1226 += 1
        if h.get("bond_status") == "eligible":
            g_bond += 1
        if h.get("habeas_relief") in FAVORABLE_RELIEF_VALUES:
            g_habeas += 1

    if global_n == 0:
        return 0

    global_rate_1226 = g_1226 / global_n
    global_rate_bond = g_bond / global_n
    global_rate_habeas = g_habeas / global_n

    prior_strength = 5.0

    buckets = defaultdict(list)
    for case, ext, h in parsed:
        judge = (case.judge_name or "").strip()
        if not judge:
            continue
        buckets[(judge, "all")].append((case, ext, h))
        if ext.is_interior_detention_focus:
            buckets[(judge, "interior_detention")].append((case, ext, h))
        if ext.is_border_or_near_border_detention:
            buckets[(judge, "near_border")].append((case, ext, h))

    db.query(JudgeIssueScore).filter(JudgeIssueScore.as_of_date == as_of).delete()

    created = 0
    for (judge, segment), items in buckets.items():
        n = len(items)
        s1226 = sum(1 for _, _, h in items if h.get("applicable_provision") == "1226")
        sbond = sum(1 for _, _, h in items if h.get("bond_status") == "eligible")
        shab = sum(1 for _, _, h in items if h.get("habeas_relief") in FAVORABLE_RELIEF_VALUES)

        r1226 = (s1226 + prior_strength * global_rate_1226) / (n + prior_strength)
        rbond = (sbond + prior_strength * global_rate_bond) / (n + prior_strength)
        rhab = (shab + prior_strength * global_rate_habeas) / (n + prior_strength)

        ci_low, ci_high = _wilson_interval(s1226, n)

        db.add(JudgeIssueScore(
            judge_name=judge,
            as_of_date=as_of,
            segment=segment,
            n_cases=n,
            rate_1226=r1226,
            rate_bond_eligible=rbond,
            rate_habeas_granted=rhab,
            ci_low=ci_low,
            ci_high=ci_high,
            model_meta={
                "prior_strength": prior_strength,
                "global_rate_1226": global_rate_1226,
                "global_rate_bond": global_rate_bond,
                "global_rate_habeas": global_rate_habeas,
                "note": "Descriptive issue-specific tendency score (not motive inference)",
            },
        ))
        created += 1

    db.commit()
    return created


def _outcome_bucket(holdings: dict | None) -> str:
    raw = ((holdings or {}).get("habeas_relief") or "").strip().lower()
    if raw in FAVORABLE_RELIEF_VALUES:
        return "favorable"
    if raw in UNFAVORABLE_RELIEF_VALUES:
        return "unfavorable"
    return "other"


def recompute_judge_phrase_scores(
    db: Session,
    as_of: date | None = None,
    min_cases: int = 2,
) -> int:
    if as_of is None:
        as_of = date.today()

    rows = db.execute(
        select(CaseRecord, CaseExtraction)
        .join(CaseExtraction, CaseExtraction.case_id == CaseRecord.id)
        .where(CaseRecord.judge_name.is_not(None))
        .where(CaseExtraction.review_status.in_(["auto", "reviewed"]))
    ).all()

    buckets: dict[tuple[str, str, str], list[dict]] = defaultdict(list)

    for case, ext in rows:
        judge = (case.judge_name or "").strip()
        if not judge:
            continue

        phrase_signals = ext.phrase_signals or []
        if not phrase_signals:
            continue

        outcome_bucket = _outcome_bucket(ext.holdings)
        segments = ["all"]
        if ext.is_interior_detention_focus:
            segments.append("interior_detention")
        if ext.is_border_or_near_border_detention:
            segments.append("near_border")

        seen_phrase_keys = set()
        for signal in phrase_signals:
            phrase_key = (signal.get("phrase_key") or "").strip()
            if not phrase_key or phrase_key in seen_phrase_keys:
                continue
            seen_phrase_keys.add(phrase_key)

            phrase_label = signal.get("phrase_label") or phrase_key
            phrase_category = signal.get("phrase_category") or "uncategorized"

            payload = {
                "case_id": case.id,
                "case_caption": case.case_caption,
                "outcome_bucket": outcome_bucket,
                "evidence": signal.get("evidence"),
                "matched_alias": signal.get("matched_alias"),
                "phrase_label": phrase_label,
                "phrase_category": phrase_category,
            }

            for segment in segments:
                buckets[(judge, segment, phrase_key)].append(payload)

    db.query(JudgePhraseScore).filter(JudgePhraseScore.as_of_date == as_of).delete()

    created = 0
    for (judge, segment, phrase_key), items in buckets.items():
        n_cases = len(items)
        if n_cases < min_cases:
            continue

        phrase_label = items[0]["phrase_label"]
        phrase_category = items[0]["phrase_category"]

        favorable_count = sum(1 for item in items if item["outcome_bucket"] == "favorable")
        unfavorable_count = sum(1 for item in items if item["outcome_bucket"] == "unfavorable")
        other_count = sum(1 for item in items if item["outcome_bucket"] == "other")

        denom = favorable_count + unfavorable_count
        favorable_rate = (favorable_count / denom) if denom else None
        unfavorable_rate = (unfavorable_count / denom) if denom else None

        if favorable_rate is not None and favorable_rate >= 0.70:
            direction = "favorable_lean"
        elif unfavorable_rate is not None and unfavorable_rate >= 0.70:
            direction = "unfavorable_lean"
        else:
            direction = "mixed"

        sample_case_ids = [item["case_id"] for item in items[:5]]
        sample_evidence = [
            {
                "case_id": item["case_id"],
                "case_caption": item["case_caption"],
                "matched_alias": item["matched_alias"],
                "evidence": item["evidence"],
                "outcome_bucket": item["outcome_bucket"],
            }
            for item in items[:5]
        ]

        db.add(JudgePhraseScore(
            judge_name=judge,
            as_of_date=as_of,
            segment=segment,
            phrase_key=phrase_key,
            phrase_label=phrase_label,
            phrase_category=phrase_category,
            n_cases=n_cases,
            favorable_count=favorable_count,
            unfavorable_count=unfavorable_count,
            other_count=other_count,
            favorable_rate=favorable_rate,
            unfavorable_rate=unfavorable_rate,
            direction=direction,
            sample_case_ids=sample_case_ids,
            sample_evidence=sample_evidence,
            model_meta={
                "min_cases": min_cases,
                "note": "Descriptive phrase-conditioned tendency score (not motive inference)",
            },
        ))
        created += 1

    db.commit()
    return created